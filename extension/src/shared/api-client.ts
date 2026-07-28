/**
 * Backend API client — POST /slides/analyze and POST /chat.
 */

import type { ChatDoneEvent, ChatErrorEvent, ChatRequest, HealthResponse, SlideAnalysisResponse } from "@shared/types";

// Port 8001, not 8000 — see docker-compose.yml's `backend.ports` comment:
// some environments have another local process already bound to
// 127.0.0.1:8000, which silently wins over Docker's published port for
// anything addressed as localhost:8000/127.0.0.1:8000.
const DEFAULT_BACKEND_URL = "http://127.0.0.1:8001";

// Must match the backend's LOCAL_API_KEY (see .env.example at the repo
// root and docs/adr/ADR-007-local-first-deployment.md). Set via the
// Settings tab (extension/src/sidepanel/tabs/SettingsTab.tsx), which
// writes to chrome.storage.local — this default only applies until then.
const DEFAULT_LOCAL_API_KEY = "change-me-to-a-random-value";

export interface BackendConfig {
  backendUrl: string;
  apiKey: string;
}

export async function getConfig(): Promise<BackendConfig> {
  const stored = await chrome.storage.local.get(["backendUrl", "apiKey"]);
  return {
    backendUrl: (stored.backendUrl as string | undefined) ?? DEFAULT_BACKEND_URL,
    apiKey: (stored.apiKey as string | undefined) ?? DEFAULT_LOCAL_API_KEY,
  };
}

export async function setConfig(config: BackendConfig): Promise<void> {
  await chrome.storage.local.set(config);
}

/**
 * GET /health — used by the Settings tab's "Test connection" button.
 * Exempt from the X-API-Key requirement (docs/API_CONTRACT.md §1), so a
 * bad connection, not a bad key, is the only reason this can fail.
 */
export async function checkHealth(backendUrl: string): Promise<HealthResponse> {
  const response = await fetch(`${backendUrl}/api/v1/health`);
  if (!response.ok) {
    throw new ApiError(`Health check failed (${response.status})`, response.status);
  }
  return (await response.json()) as HealthResponse;
}

export interface AnalyzeSlideParams {
  image: Blob;
  presentationId: string | null;
  slideNumber: number;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function analyzeSlide(params: AnalyzeSlideParams): Promise<SlideAnalysisResponse> {
  const { backendUrl, apiKey } = await getConfig();

  const formData = new FormData();
  formData.append("image", params.image, "slide.png");
  formData.append("slide_number", String(params.slideNumber));
  if (params.presentationId) {
    formData.append("presentation_id", params.presentationId);
  }

  const response = await fetch(`${backendUrl}/api/v1/slides/analyze`, {
    method: "POST",
    headers: { "X-API-Key": apiKey },
    body: formData,
  });

  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { message?: string } | null;
    throw new ApiError(body?.message ?? `Analysis request failed (${response.status})`, response.status);
  }

  return (await response.json()) as SlideAnalysisResponse;
}

export type ChatStreamEvent =
  | { type: "delta"; text: string }
  | { type: "done"; data: ChatDoneEvent }
  | { type: "error"; data: ChatErrorEvent };

function parseSseEvent(raw: string): ChatStreamEvent | null {
  let eventName = "message";
  let dataText = "";
  for (const line of raw.split("\n")) {
    if (line.startsWith("event:")) {
      eventName = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      dataText += line.slice(5).trim();
    }
  }
  if (!dataText) {
    return null;
  }

  const data = JSON.parse(dataText) as unknown;
  if (eventName === "delta") {
    return { type: "delta", text: (data as { text: string }).text };
  }
  if (eventName === "done") {
    return { type: "done", data: data as ChatDoneEvent };
  }
  if (eventName === "error") {
    return { type: "error", data: data as ChatErrorEvent };
  }
  return null;
}

/**
 * Stream POST /chat (docs/API_CONTRACT.md §3). SSE over a POST body can't
 * use EventSource (GET-only) — this reads the fetch body stream directly
 * and splits it into events on blank-line boundaries.
 */
export async function* streamChat(request: ChatRequest): AsyncGenerator<ChatStreamEvent> {
  const { backendUrl, apiKey } = await getConfig();

  const response = await fetch(`${backendUrl}/api/v1/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-API-Key": apiKey },
    body: JSON.stringify(request),
  });

  if (!response.ok || !response.body) {
    const body = (await response.json().catch(() => null)) as { message?: string } | null;
    throw new ApiError(body?.message ?? `Chat request failed (${response.status})`, response.status);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });

    let separatorIndex = buffer.indexOf("\n\n");
    while (separatorIndex !== -1) {
      const rawEvent = buffer.slice(0, separatorIndex);
      buffer = buffer.slice(separatorIndex + 2);
      const event = parseSseEvent(rawEvent);
      if (event) {
        yield event;
      }
      separatorIndex = buffer.indexOf("\n\n");
    }
  }
}
