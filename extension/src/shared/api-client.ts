/**
 * Backend API client — POST /slides/analyze and POST /chat.
 */

import type {
  AuthResponse,
  ChatDoneEvent,
  ChatErrorEvent,
  ChatRequest,
  HealthResponse,
  SlideAnalysisResponse,
} from "@shared/types";

// Port 8001, not 8000 — see docker-compose.yml's `backend.ports` comment:
// some environments have another local process already bound to
// 127.0.0.1:8000, which silently wins over Docker's published port for
// anything addressed as localhost:8000/127.0.0.1:8000.
// A hosted build bakes in its public URL instead via VITE_BACKEND_URL
// (docs/DEPLOY.md); either way the Settings tab can still override it.
const DEFAULT_BACKEND_URL = import.meta.env.VITE_BACKEND_URL || "http://127.0.0.1:8001";

// Must match the backend's LOCAL_API_KEY (see .env.example at the repo
// root and docs/adr/ADR-007-local-first-deployment.md). Set via the
// Settings tab (extension/src/sidepanel/tabs/SettingsTab.tsx), which
// writes to chrome.storage.local — this default only applies until then.
const DEFAULT_LOCAL_API_KEY = "change-me-to-a-random-value";

// "" means "Server default": no model is sent, so the backend uses whatever
// its .env configures for its active provider (OpenAI or Anthropic). A
// specific pick from the Settings tab only works against a backend of that
// provider (backend/app/api/deps.py's resolve_* functions).
const DEFAULT_MODEL = "";

export interface BackendConfig {
  backendUrl: string;
  apiKey: string;
  vlmModel: string;
  chatModel: string;
}

export async function getConfig(): Promise<BackendConfig> {
  const stored = await chrome.storage.local.get(["backendUrl", "apiKey", "vlmModel", "chatModel"]);
  return {
    backendUrl: (stored.backendUrl as string | undefined) ?? DEFAULT_BACKEND_URL,
    apiKey: (stored.apiKey as string | undefined) ?? DEFAULT_LOCAL_API_KEY,
    vlmModel: (stored.vlmModel as string | undefined) ?? DEFAULT_MODEL,
    chatModel: (stored.chatModel as string | undefined) ?? DEFAULT_MODEL,
  };
}

export async function setConfig(config: BackendConfig): Promise<void> {
  await chrome.storage.local.set(config);
}

// Sign-in state (docs/PublicHostingMVP.md Phase 2) — kept separate from
// BackendConfig above since it's identity, not backend connection config,
// and most of this codebase's existing flows (capture, chat) don't need it
// yet (the session token isn't required by any endpoint today — see
// auth.py's module docstring on why it's additive to X-API-Key, not a
// replacement).
export interface AuthState {
  sessionToken: string | null;
  email: string | null;
}

export async function getAuthState(): Promise<AuthState> {
  const stored = await chrome.storage.local.get(["sessionToken", "userEmail"]);
  return {
    sessionToken: (stored.sessionToken as string | undefined) ?? null,
    email: (stored.userEmail as string | undefined) ?? null,
  };
}

async function setAuthState(state: AuthState): Promise<void> {
  await chrome.storage.local.set({ sessionToken: state.sessionToken, userEmail: state.email });
}

/**
 * POSTs a Google access token (however it was obtained — `getAuthToken`
 * or `launchWebAuthFlow` below both produce the same kind of token) to
 * POST /auth/google, stores the resulting VisionLearn session, and
 * returns it. The backend only ever verifies "is this a valid Google
 * access token" (app/services/google_oauth.py) — it has no idea which
 * extension-side flow produced it, so both sign-in paths share this
 * exact exchange step.
 */
async function exchangeGoogleAccessToken(googleAccessToken: string): Promise<AuthState> {
  const { backendUrl, apiKey } = await getConfig();
  const response = await fetch(`${backendUrl}/api/v1/auth/google`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-API-Key": apiKey },
    body: JSON.stringify({ access_token: googleAccessToken }),
  });

  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { message?: string; detail?: string } | null;
    throw new ApiError(body?.message ?? body?.detail ?? `Sign-in failed (${response.status})`, response.status);
  }

  const auth = (await response.json()) as AuthResponse;
  const state: AuthState = { sessionToken: auth.session_token, email: auth.email };
  await setAuthState(state);
  return state;
}

/**
 * Signs in with Google via `chrome.identity.getAuthToken` — the simpler,
 * native Chrome flow (extension-side half of docs/PublicHostingMVP.md
 * Phase 2, requires the `identity` permission and the `oauth2` block in
 * manifest.json). Silently reuses whichever Google account Chrome itself
 * is signed into; it has no way to show an account picker — see
 * `signInWithGooglePicker` below for that. Throws on failure — a declined
 * consent prompt rejects here, same as a network/API failure.
 */
export async function signInWithGoogle(): Promise<AuthState> {
  const { token: googleAccessToken } = await chrome.identity.getAuthToken({ interactive: true });
  if (!googleAccessToken) {
    throw new Error("Google sign-in was cancelled or did not return a token.");
  }

  try {
    return await exchangeGoogleAccessToken(googleAccessToken);
  } catch (error) {
    // The Google token itself was obtained but the backend rejected it (or
    // couldn't verify it) — remove it from Chrome's cache so the next
    // sign-in attempt fetches a fresh one instead of retrying the same
    // already-rejected token.
    await chrome.identity.removeCachedAuthToken({ token: googleAccessToken }).catch(() => undefined);
    throw error;
  }
}

// Separate OAuth client from manifest.json's `oauth2.client_id` — a "Web
// application" type, not "Chrome Extension", since only that type supports
// `launchWebAuthFlow`'s full redirect-based consent screen (and its
// `prompt=select_account` control over the account picker, which
// `getAuthToken` never exposes). Not a secret: this flow is a public
// client (implicit grant, no client secret involved) — same reasoning as
// manifest.json's client_id being safe to ship in the extension bundle.
const WEB_OAUTH_CLIENT_ID = "156756671908-4v0eut5p9l3qc5o6pnnnillhp1n3d0d1.apps.googleusercontent.com";

/**
 * Signs in with Google via `chrome.identity.launchWebAuthFlow`, forcing
 * Google's account picker (`prompt=select_account`) regardless of which
 * account Chrome itself is already signed into — the capability
 * `signInWithGoogle` structurally can't offer. Exists alongside that
 * simpler flow, not instead of it; both end up calling the same
 * `exchangeGoogleAccessToken`, so the backend and stored session state
 * are identical either way.
 */
export async function signInWithGooglePicker(): Promise<AuthState> {
  const redirectUri = chrome.identity.getRedirectURL();
  const authUrl = new URL("https://accounts.google.com/o/oauth2/v2/auth");
  authUrl.searchParams.set("client_id", WEB_OAUTH_CLIENT_ID);
  authUrl.searchParams.set("response_type", "token");
  authUrl.searchParams.set("redirect_uri", redirectUri);
  authUrl.searchParams.set("scope", "openid email profile");
  authUrl.searchParams.set("prompt", "select_account");

  const redirectedTo = await chrome.identity.launchWebAuthFlow({ url: authUrl.toString(), interactive: true });
  if (!redirectedTo) {
    throw new Error("Google sign-in was cancelled.");
  }

  // Google returns the token in the URL fragment (implicit grant), e.g.
  // "...#access_token=...&token_type=Bearer&expires_in=3599" — never in
  // the query string, so it's parsed out of `hash`, not `searchParams`.
  const fragment = new URLSearchParams(new URL(redirectedTo).hash.slice(1));
  const googleAccessToken = fragment.get("access_token");
  if (!googleAccessToken) {
    throw new Error("Google sign-in did not return an access token.");
  }

  return exchangeGoogleAccessToken(googleAccessToken);
}

export async function signOut(): Promise<void> {
  const { backendUrl, apiKey } = await getConfig();
  const { sessionToken } = await getAuthState();

  if (sessionToken) {
    // Best-effort — if this fails (offline, server down), still clear
    // local state below so the UI reflects "signed out" either way; a
    // stray still-valid session token server-side just expires on its own
    // (SESSION_LIFETIME in sessions.py).
    await fetch(`${backendUrl}/api/v1/auth/logout`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-API-Key": apiKey },
      body: JSON.stringify({ session_token: sessionToken }),
    }).catch(() => undefined);
  }

  await chrome.identity.clearAllCachedAuthTokens().catch(() => undefined);
  await setAuthState({ sessionToken: null, email: null });
}

// A free Render web service sleeps after 15 minutes idle (docs/DEPLOY_RENDER.md)
// and takes ~30-60s to boot on the next request; until then its proxy
// answers with connection errors, 502/503/504s or an HTML holding page.
// Requests to such a backend are retried until it's up, and `onWaking` fires
// once so the UI can explain the wait. Scoped to *.onrender.com hosts so a
// local backend that's simply not running still fails immediately.
const WAKE_TIMEOUT_MS = 150_000;
const WAKE_RETRY_INTERVAL_MS = 5_000;
// Caps each individual attempt — without this, a single request that hangs
// (gets a TCP connection but no HTTP response, which happens while Render's
// proxy is still booting the instance) blocks inside `await fetch` forever:
// the deadline/retry logic below never even runs, since it only looks at
// Date.now() after a fetch settles. This is what turns a slow wake-up into
// "stuck on Checking… forever" instead of a visible retry.
//
// NOT a single shared constant: a health check should resolve almost
// instantly, but a slide analysis call legitimately takes 10-20+ seconds
// on Render's free-tier CPU (a vision model call plus DB writes) — using
// the short health-check timeout for it was a real bug (measured: ~11s of
// genuine server-side work routinely exceeded a 12s attempt timeout,
// aborting an in-flight request and restarting it from scratch, every
// time, which is what turned one ~11s analysis into 30-60s of retries).
const HEALTH_ATTEMPT_TIMEOUT_MS = 12_000;
const ANALYZE_ATTEMPT_TIMEOUT_MS = 60_000;
const CHAT_ATTEMPT_TIMEOUT_MS = 30_000;
const WAKE_STATUSES = new Set([502, 503, 504]);

function canSleep(url: string): boolean {
  try {
    return new URL(url).hostname.endsWith(".onrender.com");
  } catch {
    return false;
  }
}

function isWakingResponse(response: Response): boolean {
  // The backend's own errors are JSON (e.g. chat's 503 when no provider
  // is configured) and must surface, not be retried.
  const isJson = (response.headers.get("content-type") ?? "").includes("application/json");
  if (isJson) {
    return false;
  }
  return WAKE_STATUSES.has(response.status) || (response.ok && (response.headers.get("content-type") ?? "").includes("text/html"));
}

async function fetchWakingBackend(
  url: string,
  init: RequestInit,
  onWaking?: () => void,
  attemptTimeoutMs: number = HEALTH_ATTEMPT_TIMEOUT_MS
): Promise<Response> {
  if (!canSleep(url)) {
    return fetch(url, init);
  }
  const deadline = Date.now() + WAKE_TIMEOUT_MS;
  let notified = false;
  while (true) {
    let response: Response | null = null;
    let networkError: unknown = null;
    const timeoutController = new AbortController();
    const timeoutId = setTimeout(() => timeoutController.abort(), attemptTimeoutMs);
    try {
      response = await fetch(url, { ...init, signal: timeoutController.signal });
    } catch (error) {
      networkError = error;
    } finally {
      clearTimeout(timeoutId);
    }
    if (response && !isWakingResponse(response)) {
      return response;
    }
    if (Date.now() >= deadline) {
      if (response) {
        return response;
      }
      throw networkError;
    }
    if (!notified) {
      notified = true;
      onWaking?.();
    }
    await new Promise((resolve) => setTimeout(resolve, WAKE_RETRY_INTERVAL_MS));
  }
}

/**
 * GET /health — used by the Settings tab's "Test connection" button.
 * Exempt from the X-API-Key requirement (docs/API_CONTRACT.md §1), so a
 * bad connection, not a bad key, is the only reason this can fail.
 */
export async function checkHealth(backendUrl: string, onWaking?: () => void): Promise<HealthResponse> {
  const response = await fetchWakingBackend(`${backendUrl}/api/v1/health`, {}, onWaking, HEALTH_ATTEMPT_TIMEOUT_MS);
  if (!response.ok) {
    throw new ApiError(`Health check failed (${response.status})`, response.status);
  }
  return (await response.json()) as HealthResponse;
}

// Attached to capture/chat requests so a signed-in user's presentations
// are actually attributed to their account (docs/PublicHostingMVP.md
// Phase 3) instead of staying anonymous despite having signed in. Empty
// object when signed out — every endpoint still works without it (Phase
// 2/3 are additive, not required), it just means the resulting data has
// no owner, same as the whole app worked before sign-in existed.
async function authHeader(): Promise<Record<string, string>> {
  const { sessionToken } = await getAuthState();
  return sessionToken ? { Authorization: `Bearer ${sessionToken}` } : {};
}

export interface AnalyzeSlideParams {
  image: Blob;
  presentationId: string | null;
  slideNumber: number;
  onWaking?: () => void;
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
  const { backendUrl, apiKey, vlmModel } = await getConfig();

  const formData = new FormData();
  formData.append("image", params.image, params.image.type === "image/jpeg" ? "slide.jpg" : "slide.png");
  formData.append("slide_number", String(params.slideNumber));
  if (vlmModel) {
    formData.append("model", vlmModel);
  }
  if (params.presentationId) {
    formData.append("presentation_id", params.presentationId);
  }

  const response = await fetchWakingBackend(
    `${backendUrl}/api/v1/slides/analyze`,
    { method: "POST", headers: { "X-API-Key": apiKey, ...(await authHeader()) }, body: formData },
    params.onWaking,
    ANALYZE_ATTEMPT_TIMEOUT_MS
  );

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
export async function* streamChat(request: ChatRequest, onWaking?: () => void): AsyncGenerator<ChatStreamEvent> {
  const { backendUrl, apiKey, chatModel } = await getConfig();

  const response = await fetchWakingBackend(
    `${backendUrl}/api/v1/chat`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-API-Key": apiKey, ...(await authHeader()) },
      // request.model, when the caller already set one, wins over the
      // Settings-tab default — no caller does this today, but this keeps
      // streamChat consistent with analyzeSlide's "config unless overridden"
      // behavior rather than silently clobbering a future explicit choice.
      body: JSON.stringify({ model: chatModel || null, ...request }),
    },
    onWaking,
    CHAT_ATTEMPT_TIMEOUT_MS
  );

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
