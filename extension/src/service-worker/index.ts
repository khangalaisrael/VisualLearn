/**
 * VisionLearn AI — background service worker (MV3).
 *
 * Owns tab capture, the backend API client, and message routing between the
 * content script and the side panel (docs/ARCHITECTURE.md §3).
 */

import { ApiError, analyzeSlide, getAuthState } from "../shared/api-client";
import { LOCAL_RETENTION_DAYS, latestPresentationFor, purgeOlderThan, saveCapture } from "../shared/capture-store";
import type {
  BackendWakingMessage,
  BackgroundMessage,
  CaptureRequestMessage,
  CaptureStartedMessage,
  FigureSelectedMessage,
  OpenFigureChatMessage,
  SlideAnalysisFailedMessage,
  SlideAnalyzedMessage,
} from "./messages";
import type { SlideAnalysisResponse } from "@shared/types";

chrome.sidePanel
  .setPanelBehavior({ openPanelOnActionClick: true })
  .catch((error) => console.error("[VisionLearn] failed to set side panel behavior", error));

// Per-tab de-dupe: pressing Capture twice on an unchanged slide shouldn't
// round-trip an identical upload. Holds the last successful result per tab,
// keyed by screenshot hash, so the repeat press re-shows it. (This is not
// the server-side analysis cache.)
const lastResultByTab = new Map<number, { hash: string; result: SlideAnalysisResponse }>();

async function sha256Hex(buffer: ArrayBuffer): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", buffer);
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

// Captures are scaled (never cropped) so the long edge is at most this many
// pixels, then re-encoded as JPEG. Claude downscales larger images to about
// this size before reading them anyway, so detail isn't lost — but the
// upload shrinks ~5-10x, which cuts upload time on campus Wi-Fi, CPU work on
// a small hosted backend, and per-capture token cost. Bounding boxes come
// back normalized (0-1, prompts/analysis.v4.md), so overlays are unaffected.
const MAX_UPLOAD_LONG_EDGE_PX = 1568;
const UPLOAD_JPEG_QUALITY = 0.9;

// The small picture kept on this device for "Recent" (never uploaded).
const THUMBNAIL_LONG_EDGE_PX = 320;
const THUMBNAIL_JPEG_QUALITY = 0.7;

/** Scales a bitmap down (never up, never cropped) and encodes it as JPEG. */
async function renderJpeg(bitmap: ImageBitmap, maxLongEdge: number, quality: number): Promise<Blob | null> {
  const scale = Math.min(1, maxLongEdge / Math.max(bitmap.width, bitmap.height));
  const width = Math.max(1, Math.round(bitmap.width * scale));
  const height = Math.max(1, Math.round(bitmap.height * scale));

  const canvas = new OffscreenCanvas(width, height);
  const context = canvas.getContext("2d");
  if (!context) return null;
  context.imageSmoothingQuality = "high";
  context.drawImage(bitmap, 0, 0, width, height);
  return canvas.convertToBlob({ type: "image/jpeg", quality });
}

/** Title and address of the tab, read before the screenshot so they describe
 * the same page. The address loses its query string and fragment: those often
 * carry tokens, and they don't identify the lecture. */
async function readLecture(tabId: number): Promise<{ title: string; pageUrl: string; lectureKey: string }> {
  try {
    const tab = await chrome.tabs.get(tabId);
    const url = new URL(tab.url ?? "");
    if (url.protocol !== "http:" && url.protocol !== "https:") {
      return { title: tab.title?.trim() ?? "", pageUrl: "", lectureKey: "" };
    }
    const pageUrl = `${url.origin}${url.pathname}`;
    return { title: tab.title?.trim() || url.hostname, pageUrl, lectureKey: pageUrl.toLowerCase() };
  } catch {
    return { title: "", pageUrl: "", lectureKey: "" };
  }
}

async function analyzeWithLecture(
  image: Blob,
  message: CaptureRequestMessage,
  lecture: { title: string; pageUrl: string },
  presentationId: string | null
): Promise<SlideAnalysisResponse> {
  const attempt = (id: string | null) =>
    analyzeSlide({
      image,
      presentationId: id,
      slideNumber: message.slideNumber,
      lectureTitle: lecture.title,
      pageUrl: lecture.pageUrl,
      onWaking: () => {
        const waking: BackendWakingMessage = { type: "BACKEND_WAKING" };
        chrome.runtime.sendMessage(waking).catch(() => undefined);
      },
    });
  try {
    return await attempt(presentationId);
  } catch (error) {
    // The remembered presentation is gone (expired, deleted) or belongs to
    // someone else who used this browser: start a fresh one rather than fail.
    if (presentationId && message.presentationId === null && error instanceof ApiError && error.status === 404) {
      return attempt(null);
    }
    throw error;
  }
}

// A different account (or signing out) must never be handed the previous
// account's cached result for an unchanged screen.
chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "local" && (changes.sessionToken || changes.userEmail)) {
    lastResultByTab.clear();
  }
});

async function handleCaptureRequest(message: CaptureRequestMessage, tabId: number): Promise<void> {
  const started: CaptureStartedMessage = { type: "CAPTURE_STARTED" };
  chrome.runtime.sendMessage(started).catch(() => undefined);

  const lecture = await readLecture(tabId);
  const owner = ((await getAuthState()).email ?? "").toLowerCase();
  const dataUrl = await chrome.tabs.captureVisibleTab({ format: "png" });
  const imageBlob = await (await fetch(dataUrl)).blob();
  const imageHash = await sha256Hex(await imageBlob.arrayBuffer());

  const previous = lastResultByTab.get(tabId);
  if (previous?.hash === imageHash) {
    // Unchanged screen: answer from memory (no upload, no quota used). It
    // used to return silently, leaving the panel on "Analyzing…" forever.
    deliverResult(previous.result, tabId);
    return;
  }

  try {
    const bitmap = await createImageBitmap(imageBlob);
    let upload: Blob;
    let thumbnail: Blob | null;
    try {
      upload = (await renderJpeg(bitmap, MAX_UPLOAD_LONG_EDGE_PX, UPLOAD_JPEG_QUALITY)) ?? imageBlob;
      thumbnail = await renderJpeg(bitmap, THUMBNAIL_LONG_EDGE_PX, THUMBNAIL_JPEG_QUALITY).catch(() => null);
    } finally {
      bitmap.close();
    }

    // A signed-out capture of a page seen before joins that lecture's group;
    // signed-in captures are grouped by the server as well.
    const presentationId = message.presentationId ?? (await latestPresentationFor(lecture.lectureKey, owner).catch(() => null));
    const result = await analyzeWithLecture(upload, message, lecture, presentationId);

    // Remembered only on success, so a failed capture (a usage limit, a
    // network error) can be retried on the same slide.
    lastResultByTab.set(tabId, { hash: imageHash, result });
    deliverResult(result, tabId);

    // Best effort: a failure here must never hide a result the user already has.
    await saveCapture({
      slide_id: result.slide_id,
      presentation_id: result.presentation_id,
      lectureKey: lecture.lectureKey,
      title: lecture.title || "Untitled capture",
      url: lecture.pageUrl,
      thumbnail,
      summary: result.summary.slice(0, 400),
      capturedAt: Date.now(),
      owner,
    }).catch((error) => console.warn("[VisionLearn] couldn't save the capture locally", error));
    void purgeOlderThan(LOCAL_RETENTION_DAYS).catch(() => undefined);
  } catch (error) {
    console.error("[VisionLearn] slide analysis failed", error);
    const outgoing: SlideAnalysisFailedMessage = {
      type: "SLIDE_ANALYSIS_FAILED",
      message: error instanceof Error ? error.message : String(error),
      ...(error instanceof ApiError ? { limitKind: error.limitKind, retryAfterSeconds: error.retryAfterSeconds } : {}),
    };
    chrome.runtime.sendMessage(outgoing).catch(() => undefined);
  }
}

function deliverResult(result: SlideAnalysisResponse, tabId: number): void {
  const outgoing: SlideAnalyzedMessage = { type: "SLIDE_ANALYZED", result };
  // chrome.runtime.sendMessage only reaches extension pages (the side
  // panel); it does NOT reach a content script in a tab — that needs
  // chrome.tabs.sendMessage(tabId, ...) instead (found live-testing the
  // overlay renderer: the content script's listener never fired without
  // this). Both are sent so the side panel's object list and the
  // content script's overlay (content-script/overlay.ts) stay in sync.
  chrome.runtime.sendMessage(outgoing).catch(() => {
    // No side panel listening (e.g. not open yet) — that's fine.
  });
  chrome.tabs.sendMessage(tabId, outgoing).catch(() => {
    // No content script listening on this tab (e.g. a chrome:// page) —
    // fine, there's simply no overlay to draw there.
  });
}

async function resolveActiveTabId(): Promise<number | undefined> {
  const [activeTab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return activeTab?.id;
}

// Storage key for the handoff described in handleOpenFigureChat's comment.
const PENDING_FIGURE_SELECTION_KEY = "pendingFigureSelection";

async function handleOpenFigureChat(message: OpenFigureChatMessage, tab: chrome.tabs.Tab | undefined): Promise<void> {
  const outgoing: FigureSelectedMessage = {
    type: "FIGURE_SELECTED",
    slide: message.slide,
    objectId: message.objectId,
  };

  // chrome.sidePanel.open() isn't available to content scripts (only
  // extension pages/the service worker), which is why this round-trips
  // through here instead of the content script calling it directly. It
  // must be called synchronously-ish off the user gesture that triggered
  // this message, before any other await — see MDN's sidePanel.open docs.
  if (tab?.windowId !== undefined) {
    await chrome.sidePanel.open({ windowId: tab.windowId }).catch((error) => {
      console.error("[VisionLearn] failed to open side panel", error);
    });
  }

  // If the panel was already open, this reaches its listener directly.
  // If we just opened it above, its listener won't be registered yet —
  // same race the capture flow already handles (see the comment on
  // SLIDE_ANALYZED above) — so also persist it for the panel to pick up
  // on mount (AskTab.tsx), then clear it once consumed.
  chrome.runtime.sendMessage(outgoing).catch(() => undefined);
  await chrome.storage.local.set({ [PENDING_FIGURE_SELECTION_KEY]: outgoing });
}

// Keyboard capture (Alt+Shift+S by default; users can change it at
// chrome://extensions/shortcuts). The side panel can only be opened from a
// user gesture, and the shortcut is one, so it is opened before anything else.
chrome.commands.onCommand.addListener((command, tab) => {
  if (command !== "capture-slide" || tab?.id === undefined) return;
  if (tab.windowId !== undefined) {
    chrome.sidePanel.open({ windowId: tab.windowId }).catch(() => undefined);
  }
  void handleCaptureRequest({ type: "CAPTURE_REQUEST", presentationId: null, slideNumber: 1 }, tab.id);
});

chrome.runtime.onMessage.addListener((message: BackgroundMessage, sender) => {
  if (message.type === "OPEN_FIGURE_CHAT") {
    void handleOpenFigureChat(message, sender.tab);
    return false;
  }

  if (message.type !== "CAPTURE_REQUEST") {
    return false;
  }

  // Messages from a content script carry `sender.tab`; messages from the
  // side panel's manual "Capture Now" button do not, so resolve the active
  // tab in that case instead.
  if (sender.tab?.id !== undefined) {
    void handleCaptureRequest(message, sender.tab.id);
  } else {
    void resolveActiveTabId().then((tabId) => {
      if (tabId !== undefined) {
        void handleCaptureRequest(message, tabId);
      }
    });
  }

  return false;
});
