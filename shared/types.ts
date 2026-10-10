/**
 * Hand-written mirror of backend/app/models/schemas.py — see ./README.md.
 *
 * Covers the endpoints implemented so far (GET /health, POST
 * /slides/analyze, POST /chat). Keep this in sync as the backend's
 * schemas.py grows.
 */

export type ObjectType =
  | "title"
  | "paragraph"
  | "equation"
  | "diagram"
  | "graph"
  | "table"
  | "image"
  | "code";

export interface BoundingBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface SlideObject {
  id: string;
  type: ObjectType;
  bounding_box: BoundingBox;
  extracted_text: string | null;
  latex: string | null;
  // Only for "code" objects (the programming language, e.g. "python"),
  // null otherwise — same pattern as `latex`.
  language: string | null;
  summary: string | null;
  confidence: number;
}

export interface SlideAnalysisResponse {
  presentation_id: string;
  slide_id: string;
  cache_hit: boolean;
  status: "analyzed" | "pending" | "failed";
  objects: SlideObject[];
  summary: string;
}

export type QueryMode = "figure" | "slide" | "algorithm" | "presentation" | "general" | "auto";

// docs/TheoryOfAlgorithm.md §24 / docs/AlgorithmsMVP.md Phase 5. Only
// consulted server-side for query_mode === "algorithm" — other modes
// ignore this field.
export type ExplanationMode = "simple" | "university" | "rigorous" | "exam" | "socratic";

export interface ChatRequest {
  conversation_id: string | null;
  presentation_id: string | null;
  query_mode: QueryMode;
  slide_id: string | null;
  object_id: string | null;
  message: string;
  // Optional per-request model override ("gpt-4o" / "gpt-4o-mini" on an
  // OpenAI backend, "claude-haiku-5-5" / "claude-sonnet-5-5" on an Anthropic
  // one), set from the Settings tab's Chat Model picker. null/omitted keeps
  // the server-configured default.
  model?: string | null;
  // Only meaningful for query_mode === "algorithm"; omit for other modes.
  explanation_mode?: ExplanationMode;
}

export interface ChatUsage {
  input_tokens: number;
  output_tokens: number;
  cache_read_input_tokens: number;
}

export interface ChatDoneEvent {
  conversation_id: string;
  message_id: string;
  referenced_object_ids: string[];
  usage: ChatUsage;
}

export interface ChatErrorEvent {
  error: string;
  message: string;
}

export interface HealthResponse {
  status: "ok" | "degraded";
  db: boolean;
  cache: boolean;
  model_provider: boolean;
}

export interface ErrorResponse {
  error: string;
  message: string;
  request_id: string;
}

export interface GoogleAuthRequest {
  access_token: string;
}

export interface AuthResponse {
  session_token: string;
  email: string | null;
}

export interface LogoutRequest {
  session_token: string;
}

export type LimitKind = "daily" | "monthly" | "global";

export interface UsageWindow {
  used: number;
  limit: number;
  // ISO timestamp (UTC) of the next reset.
  resets_at: string;
}

export interface UsageResponse {
  signed_in: boolean;
  is_admin: boolean;
  unlimited: boolean;
  captures_today: UsageWindow;
  captures_month: UsageWindow;
  chat_today: UsageWindow;
  global_blocked: boolean;
}

export type WaitlistSource = "daily" | "monthly" | "settings";

export interface ConversationSummary {
  id: string;
  title: string;
  last_activity_at: string;
}

export interface ConversationListResponse {
  retention_days: number;
  conversations: ConversationSummary[];
}

export interface ConversationMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

export interface ConversationDetail {
  id: string;
  title: string;
  slide: SlideAnalysisResponse | null;
  messages: ConversationMessage[];
}

export interface CaptureConversation {
  id: string;
  title: string;
  message_count: number;
  last_activity_at: string;
}

export interface CaptureSummary {
  slide_id: string;
  slide_number: number;
  summary: string;
  created_at: string;
  conversations: CaptureConversation[];
}

export interface LectureSummary {
  id: string;
  title: string;
  page_url: string | null;
  last_activity_at: string;
  captures: CaptureSummary[];
}

export interface LectureListResponse {
  retention_days: number;
  lectures: LectureSummary[];
}

export interface AdminDay {
  date: string;
  captures: number;
  chats: number;
  cost_usd: number;
  limit_hits: number;
}

export interface AdminOverview {
  generated_at: string;
  timezone: string;
  global_captures_today: number;
  global_cap: number;
  cost_today_usd: number;
  cost_month_usd: number;
  cost_30d_usd: number;
  active_users_today: number;
  total_users: number;
  limit_hits_today: number;
  waitlist_clicks: number;
  waitlist_users: number;
  days: AdminDay[];
}

export interface AdminUser {
  user_id: string | null;
  email: string | null;
  captures_30d: number;
  chats_30d: number;
  input_tokens: number;
  output_tokens: number;
  cost_30d_usd: number;
  limit_hits_30d: number;
  last_active: string | null;
  is_outlier: boolean;
  is_admin: boolean;
}

export interface AdminUsersResponse {
  median_cost_usd: number;
  users: AdminUser[];
}

export interface AdminWaitlistEntry {
  email: string | null;
  clicks: number;
  first_click: string;
  last_click: string;
  sources: string[];
}

export interface AdminWaitlistResponse {
  unique_users: number;
  total_clicks: number;
  entries: AdminWaitlistEntry[];
}
