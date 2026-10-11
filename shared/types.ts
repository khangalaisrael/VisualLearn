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

export type ContentKind = "lecture" | "practice";

/** Where the sorter filed one capture: category > series, plus this slide's own subtopic. */
export interface SeriesRef {
  id: string;
  category: string;
  title: string;
  subtopic: string | null;
  kind: ContentKind;
}

export interface SlideAnalysisResponse {
  presentation_id: string;
  slide_id: string;
  cache_hit: boolean;
  status: "analyzed" | "pending" | "failed";
  objects: SlideObject[];
  summary: string;
  // Null for a signed-out capture, or one the sorter could not place.
  series: SeriesRef | null;
}

export type QueryMode = "figure" | "slide" | "algorithm" | "tutor" | "presentation" | "general" | "auto";

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
  // Only for query_mode === "tutor": the quiz question being discussed and
  // the option the student chose (null if they skipped it).
  quiz_id?: string;
  question_index?: number;
  selected_index?: number | null;
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
  invite_only: boolean;
  allowed: boolean;
  invite_contact: string | null;
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

export interface SeriesCapture {
  slide_id: string;
  summary: string;
  subtopic: string | null;
  kind: ContentKind;
  created_at: string;
  page_title: string;
  page_url: string | null;
  conversations: CaptureConversation[];
}

export interface SeriesSummary {
  id: string;
  category: string;
  title: string;
  cover_slide_id: string | null;
  // Marked as a favourite by its owner.
  starred: boolean;
  last_activity_at: string;
  captures: SeriesCapture[];
}

export interface SeriesListResponse {
  retention_days: number;
  series: SeriesSummary[];
  // Captures the sorter has not placed yet.
  unsorted: SeriesCapture[];
}

export interface SeriesUpdateRequest {
  title?: string;
  category?: string;
  cover_slide_id?: string;
  starred?: boolean;
}

/** An existing series (`series_id`), or a new one (`category` and `title`). */
export interface MoveSlideRequest {
  series_id?: string;
  category?: string;
  title?: string;
}

export interface NoteOut {
  id: string;
  title: string;
  body: string;
  source: "ai" | "user";
  // The series the note is filed under (its name when the note was made, if the series is gone).
  topic: string | null;
  // That series' category; null when the note has no series or the series is gone.
  category: string | null;
  // Marked as a favourite by its owner.
  starred: boolean;
  // Whether the series it is filed under is a favourite (the same star Recent shows).
  series_starred: boolean;
  series_id: string | null;
  slide_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface NoteListResponse {
  notes: NoteOut[];
}

export interface NoteCreateRequest {
  title?: string;
  body: string;
  source: "ai" | "user";
  series_id?: string;
  slide_id?: string;
}

export interface NoteUpdateRequest {
  title?: string;
  body?: string;
  starred?: boolean;
}

export interface QuizQuestion {
  question: string;
  options: string[];
  correct_index: number;
  explanation: string;
  slide_id: string | null;
}

export interface QuizResource {
  title: string;
  url: string;
  why: string;
}

export interface QuizSummary {
  id: string;
  title: string;
  question_count: number;
  created_at: string;
  attempts: number;
  best_score: number | null;
}

export interface QuizOut extends QuizSummary {
  series_id: string;
  questions: QuizQuestion[];
  resources: QuizResource[];
}

export interface QuizListResponse {
  quizzes: QuizSummary[];
}

export interface QuizCreateRequest {
  count: number;
  research: boolean;
}

export interface QuizAttemptResponse {
  score: number;
  total: number;
}

export type StudyAidKind = "guide" | "cheatsheet" | "flashcards";

export interface Flashcard {
  front: string;
  back: string;
}

export interface StudyAidSummary {
  id: string;
  kind: StudyAidKind;
  title: string;
  created_at: string;
  // Flashcards only: how many cards, and how many are marked as known.
  card_count: number | null;
  known_count: number | null;
}

export interface StudyAidOut extends StudyAidSummary {
  series_id: string;
  // The guide or cheat sheet text; null for flashcards.
  markdown: string | null;
  // The deck; null for the two documents.
  cards: Flashcard[] | null;
  // Positions (from 0) of the cards marked as known.
  known: number[];
}

export interface StudyAidListResponse {
  aids: StudyAidSummary[];
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
