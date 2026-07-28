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

export type BackgroundMessage = CaptureRequestMessage;
export type SidePanelMessage = SlideAnalyzedMessage | SlideAnalysisFailedMessage;
