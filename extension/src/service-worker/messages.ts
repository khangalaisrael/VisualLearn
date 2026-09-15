/**
 * Typed message contracts between content script, service worker, and side
 * panel (docs/ARCHITECTURE.md §3: "service worker... routes messages
 * between content script and side panel").
 */

import type { SlideAnalysisResponse } from "@shared/types";

export interface CaptureRequestMessage {
  type: "CAPTURE_REQUEST";
  presentationId: string | null;
  slideNumber: number;
}

export interface SlideAnalyzedMessage {
  type: "SLIDE_ANALYZED";
  result: SlideAnalysisResponse;
}

export interface SlideAnalysisFailedMessage {
  type: "SLIDE_ANALYSIS_FAILED";
  message: string;
}

/**
 * Sent by the content script's overlay renderer (docs/VisionLearn_Premium_UI_Guide.md's
 * ObjectOverlay/FloatingToolbar) when the student clicks a selected
 * figure's "Ask about this" button. The service worker opens the side
 * panel (content scripts can't call chrome.sidePanel.open themselves)
 * and relays a FigureSelectedMessage to it.
 *
 * Carries the full `slide` analysis result, not just its id — the side
 * panel may not have been open (and so never received the original
 * SLIDE_ANALYZED broadcast) when this figure was clicked, and needs
 * enough here to reconstruct its "loaded" state from scratch.
 */
export interface OpenFigureChatMessage {
  type: "OPEN_FIGURE_CHAT";
  slide: SlideAnalysisResponse;
  objectId: string;
}

export interface FigureSelectedMessage {
  type: "FIGURE_SELECTED";
  slide: SlideAnalysisResponse;
  objectId: string;
}

export type BackgroundMessage = CaptureRequestMessage | OpenFigureChatMessage;
export type SidePanelMessage = SlideAnalyzedMessage | SlideAnalysisFailedMessage | FigureSelectedMessage;
