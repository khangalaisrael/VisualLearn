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
  // Optional per-request OpenAI model override ("gpt-4o" / "gpt-4o-mini"),
  // set from the Settings tab's Chat Model picker. null/omitted keeps the
  // server-configured default.
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
