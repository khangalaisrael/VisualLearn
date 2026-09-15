/**
 * Content script entrypoint.
 *
 * Capture is manual-only (the side panel's "Capture Current Slide"
 * button, see sidepanel/tabs/AskTab.tsx, sends CAPTURE_REQUEST directly
 * via chrome.runtime). An earlier version of this file auto-triggered
 * captures on DOM-mutation bursts, which fired on ordinary page churn,
 * not just slide changes, silently burning analysis calls while browsing
 * any page. Removed by direct request rather than tuned.
 *
 * Renders the ObjectOverlay (overlay.ts) once a capture on this tab
 * comes back analyzed, so the student can click a specific figure on the
 * actual page instead of only picking from the sidepanel's object list.
 */

import { showSlideOverlay } from "./overlay";
import type { SidePanelMessage } from "../service-worker/messages";

chrome.runtime.onMessage.addListener((message: SidePanelMessage) => {
  if (message.type === "SLIDE_ANALYZED") {
    showSlideOverlay(message.result);
  }
  return false;
});
