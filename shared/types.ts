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
  | "image";

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

export type QueryMode = "figure" | "slide" | "presentation" | "general" | "auto";

export interface ChatRequest {
  conversation_id: string | null;
  presentation_id: string | null;
  query_mode: QueryMode;
  slide_id: string | null;
  object_id: string | null;
  message: string;
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
