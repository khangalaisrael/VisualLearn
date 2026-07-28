/**
 * VisionLearn AI — background service worker (MV3).
 *
 * Owns tab capture, the backend API client, and message routing between the
 * content script and the side panel (docs/ARCHITECTURE.md §3).
 */

import { analyzeSlide } from "../shared/api-client";
import type {
  BackgroundMessage,
  CaptureRequestMessage,
  SlideAnalysisFailedMessage,
  SlideAnalyzedMessage,
} from "./messages";

chrome.sidePanel
  .setPanelBehavior({ openPanelOnActionClick: true })
  .catch((error) => console.error("[VisionLearn] failed to set side panel behavior", error));

// Per-tab de-dupe: clicking "Capture Current Slide" twice in a row on an
// unchanged slide shouldn't round-trip an identical upload. This is not
// the analysis cache, which lands server-side in Milestone 2.
const lastHashByTab = new Map<number, string>();

async function sha256Hex(buffer: ArrayBuffer): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", buffer);
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

async function handleCaptureRequest(message: CaptureRequestMessage, tabId: number): Promise<void> {
  const dataUrl = await chrome.tabs.captureVisibleTab({ format: "png" });
  const imageBlob = await (await fetch(dataUrl)).blob();
  const imageHash = await sha256Hex(await imageBlob.arrayBuffer());

  if (lastHashByTab.get(tabId) === imageHash) {
    return;
  }
  lastHashByTab.set(tabId, imageHash);

  try {
    const result = await analyzeSlide({
      image: imageBlob,
      presentationId: message.presentationId,
      slideNumber: message.slideNumber,
    });

    const outgoing: SlideAnalyzedMessage = { type: "SLIDE_ANALYZED", result };
    chrome.runtime.sendMessage(outgoing).catch(() => {
      // No side panel listening (e.g. not open yet) — that's fine, the
      // side panel re-requests a capture when the user opens it.
    });
  } catch (error) {
    console.error("[VisionLearn] slide analysis failed", error);
    const outgoing: SlideAnalysisFailedMessage = {
      type: "SLIDE_ANALYSIS_FAILED",
      message: error instanceof Error ? error.message : String(error),
    };
    chrome.runtime.sendMessage(outgoing).catch(() => undefined);
  }
}

async function resolveActiveTabId(): Promise<number | undefined> {
  const [activeTab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return activeTab?.id;
}

chrome.runtime.onMessage.addListener((message: BackgroundMessage, sender) => {
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
