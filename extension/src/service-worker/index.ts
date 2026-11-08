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
  SlideAnalysisFailedMessage,
  SlideAnalyzedMessage,
} from "./messages";
import type { SlideAnalysisResponse } from "@shared/types";

// The icon click is handled here (chrome.action.onClicked below) rather than
// by Chrome opening the panel itself: with openPanelOnActionClick the click
// didn't hand this extension the activeTab grant, so every capture failed.
// It has no host permissions, so that grant is its only way to see a tab.
chrome.sidePanel
  .setPanelBehavior({ openPanelOnActionClick: false })
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

// Captures run one at a time, in the order they were asked for. Two quick
// captures (the shortcut pressed twice while paging through slides) would
// otherwise be sorted at the same moment, each unaware of the series the
// other is about to create.
let captureQueue: Promise<void> = Promise.resolve();

function enqueueCapture(message: CaptureRequestMessage, tabId: number): void {
  captureQueue = captureQueue.then(() => handleCaptureRequest(message, tabId));
}

async function handleCaptureRequest(message: CaptureRequestMessage, tabId: number): Promise<void> {
  const started: CaptureStartedMessage = { type: "CAPTURE_STARTED" };
  chrome.runtime.sendMessage(started).catch(() => undefined);

  // Everything is inside the try: a screenshot Chrome refuses to take (a
  // chrome:// page, a tab mid-navigation) must reach the panel as an error,
  // not leave it on "Analyzing…".
  try {
    const lecture = await readLecture(tabId);
    const owner = ((await getAuthState()).email ?? "").toLowerCase();
    const dataUrl = await chrome.tabs.captureVisibleTab({ format: "png" });
    const imageBlob = await (await fetch(dataUrl)).blob();
    const imageHash = await sha256Hex(await imageBlob.arrayBuffer());

    const previous = lastResultByTab.get(tabId);
    if (previous?.hash === imageHash) {
      // Unchanged screen: answer from memory (no upload, no quota used).
      deliverResult(previous.result);
      return;
    }

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
    deliverResult(result);

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
      message: captureErrorMessage(error),
      ...(error instanceof ApiError ? { limitKind: error.limitKind, retryAfterSeconds: error.retryAfterSeconds } : {}),
    };
    chrome.runtime.sendMessage(outgoing).catch(() => undefined);
  }
}

// Nothing is ever drawn on, injected into, or listened for on the page
// itself: the result goes to the side panel only, so a site has nothing of
// ours in its DOM to notice. Figures are picked in the panel's list.
function deliverResult(result: SlideAnalysisResponse): void {
  const outgoing: SlideAnalyzedMessage = { type: "SLIDE_ANALYZED", result };
  chrome.runtime.sendMessage(outgoing).catch(() => {
    // No side panel listening (e.g. not open yet) — that's fine.
  });
}

/** Chrome's own wording when a capture runs without the activeTab grant
 * (the tab moved to a new page since the icon was clicked) means nothing
 * to a student, so it is replaced with what to do about it. */
function captureErrorMessage(error: unknown): string {
  const text = error instanceof Error ? error.message : String(error);
  return /activeTab|<all_urls>/.test(text)
    ? "This page changed since you last clicked the VisionLearn icon. Click the icon in the toolbar to capture it."
    : text;
}

// Clicking the icon opens the panel and captures this tab at once. The click
// grants activeTab on this tab until it moves to a new page, so the panel's
// Capture button keeps working while the student pages through the slides.
// sidePanel.open must come before any await, while the gesture still counts.
chrome.action.onClicked.addListener((tab) => {
  if (tab.windowId !== undefined) {
    chrome.sidePanel.open({ windowId: tab.windowId }).catch(() => undefined);
  }
  if (tab.id !== undefined) {
    enqueueCapture({ type: "CAPTURE_REQUEST", presentationId: null, slideNumber: 1 }, tab.id);
  }
});

async function resolveActiveTabId(): Promise<number | undefined> {
  const [activeTab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return activeTab?.id;
}

// Keyboard capture. No key is bound by default: Chrome swallows a bound key
// before the page sees it, which a site could notice, so a student who wants
// one sets it at chrome://extensions/shortcuts. The side panel can only be opened from a
// user gesture, and the shortcut is one, so it is opened before anything else.
chrome.commands.onCommand.addListener((command, tab) => {
  if (command !== "capture-slide" || tab?.id === undefined) return;
  if (tab.windowId !== undefined) {
    chrome.sidePanel.open({ windowId: tab.windowId }).catch(() => undefined);
  }
  enqueueCapture({ type: "CAPTURE_REQUEST", presentationId: null, slideNumber: 1 }, tab.id);
});

chrome.runtime.onMessage.addListener((message: BackgroundMessage, sender) => {
  if (message.type !== "CAPTURE_REQUEST") {
    return false;
  }

  // Messages from a content script carry `sender.tab`; messages from the
  // side panel's manual "Capture Now" button do not, so resolve the active
  // tab in that case instead.
  if (sender.tab?.id !== undefined) {
    enqueueCapture(message, sender.tab.id);
  } else {
    void resolveActiveTabId().then((tabId) => {
      if (tabId !== undefined) {
        enqueueCapture(message, tabId);
      }
    });
  }

  return false;
});
