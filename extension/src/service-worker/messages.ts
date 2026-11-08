/**
 * Typed message contracts between the service worker and the side panel.
 * Nothing runs in web pages, so no message ever goes to or from a tab.
 */

import type { SlideAnalysisResponse, LimitKind } from "@shared/types";

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
  // Set when the backend refused the capture over a usage limit (HTTP 429):
  // which limit, and how long until it lifts, so the panel can show the
  // right card with a live countdown instead of a generic error.
  limitKind?: LimitKind;
  retryAfterSeconds?: number;
}

/** A capture has begun (from the Capture button or the keyboard shortcut), so
 * the panel can show "Analyzing…" even when it didn't start the capture. */
export interface CaptureStartedMessage {
  type: "CAPTURE_STARTED";
}

/** The backend is a sleeping hosted service (Render free tier) that's booting (see
 * api-client.ts's fetchWakingBackend) — the capture is still in flight. */
export interface BackendWakingMessage {
  type: "BACKEND_WAKING";
}

/** The slide summary so far, while the analysis is still being written. */
export interface SlideSummaryPartialMessage {
  type: "SLIDE_SUMMARY_PARTIAL";
  summary: string;
}

export type BackgroundMessage = CaptureRequestMessage;
export type SidePanelMessage =
  | CaptureStartedMessage
  | SlideAnalyzedMessage
  | SlideAnalysisFailedMessage
  | BackendWakingMessage
  | SlideSummaryPartialMessage;
