# VisionLearn AI — API Contract

Status: Draft v1 · Companion docs: [ARCHITECTURE.md](./ARCHITECTURE.md) · [DATA_MODEL.md](./DATA_MODEL.md)

Base path: `/api/v1`. All request/response bodies are JSON except `POST /slides/analyze` (multipart) and `POST /chat` (SSE response stream). Shapes below are described as Pydantic-style schemas for review — not implementation code.

## 1. Conventions

- **Error envelope** (all endpoints, non-2xx):
  ```
  ErrorResponse:
    error: str            # machine-readable code, e.g. "slide_analysis_failed"
    message: str          # human-readable, safe to show in the sidebar
    request_id: str
  ```
- **IDs** are UUIDs (string form) everywhere.
- **Auth (implemented, local-first form):** every endpoint except `GET /health` requires an `X-API-Key` header matching the backend's configured `LOCAL_API_KEY` (see [ADR-007](./adr/ADR-007-local-first-deployment.md)); a missing or wrong key returns `401`. `GET /health` is deliberately exempt so container healthchecks don't need the secret. This is the local-first form of auth — an `Authorization: Bearer <token>` scheme for hosted multi-user mode remains a future, additive change, not a replacement for this header.
- **Rate limiting (reserved):** `X-RateLimit-Limit` / `X-RateLimit-Remaining` response headers are reserved but not enforced locally.

## 2. `POST /slides/analyze`

Analyze a captured slide image. Called by the extension's service worker on slide change.

**Request** (`multipart/form-data`):
```
image: file                     # PNG/JPEG capture
presentation_id: str | null     # null → creates a new presentation
slide_number: int
```

**Implementation note (Sprint 1):** an earlier draft of this contract had
the client send a precomputed `image_hash`. The backend now derives the
hash itself (SHA-256 over the received bytes) instead of trusting a
client-supplied value — a hash that didn't match its bytes would silently
poison the analysis cache, and recomputing costs one cheap hash pass over
bytes already in memory. The extension may still compute its own hash
client-side for local de-duplication (e.g. skipping an upload for a slide
identical to the last one shown in the same tab), but that value is never
sent to the backend.

**`cache_hit` semantics (Milestone 2):** `cache_hit` reflects whether the
*analysis* was served from the image-hash-keyed cache
(`backend/app/services/cache_service.py`) — a global lookup, independent of
which presentation the slide belongs to. It is **not** the same as whether
a `Slide` row already existed in this presentation (a separate,
presentation-scoped de-duplication concern — see
[DATA_MODEL.md](./DATA_MODEL.md) `slides`). The two usually agree (re-showing
the same slide in the same deck is both), but can diverge: an identical
screenshot reappearing in a *different* presentation is a cache hit with a
brand-new `slide_id`.

**Response `200`:**
```
SlideAnalysisResponse:
  presentation_id: str
  slide_id: str
  cache_hit: bool
  status: "analyzed" | "pending" | "failed"
  objects: list[SlideObject]
  summary: str

SlideObject:
  id: str
  type: "title" | "paragraph" | "equation" | "diagram" | "graph" | "table" | "image"
  bounding_box: { x: float, y: float, width: float, height: float }   # normalized 0-1
  extracted_text: str | null
  latex: str | null
  summary: str | null
  confidence: float
  graph_structure: GraphStructure | null   # only populated for node/edge graph diagrams

GraphStructure:
  nodes: list[str]              # node labels
  edges: list[GraphEdge]

GraphEdge:
  node_a: str
  node_b: str
  weight: float | null           # null if the edge has no visible weight annotation
  direction: "a_to_b" | "b_to_a" | "bidirectional" | "undirected"   # see note below
```

**`graph_structure` (Milestone 2 addendum):** populated by a hybrid, two-pass VLM + classical-CV
pipeline (`backend/app/services/graph_topology.py`), not by the vision model alone — see
[ADR-010](./adr/ADR-010-hybrid-graph-structure-extraction.md) for why: pure VLM edge-attribution
measured ~69-75% accuracy on graphs with crossing lines, vs. reliably-correct topology for the
hybrid approach, confirmed across multiple fresh live API calls on real coursework slides (not just
synthetic renders). Only set when the VLM identifies the object as a node/edge graph diagram; `null`
for every other object type.

**`direction`:** determined by classical CV, never asked of the VLM — checks each edge's two
endpoints for an arrowhead's actual geometric signature (perpendicular ink width narrowing as you
move away from the node; an arrowhead is a filled triangle, wide near the node, that narrows to
the line's constant width a short distance out — a plain line has no such narrowing). Detects
`"bidirectional"` (arrowhead at both ends) alongside the one-sided cases. When neither end shows
that narrowing signature, `"undirected"` is reported rather than a guess — see
[ADR-010](./adr/ADR-010-hybrid-graph-structure-extraction.md) for the calibration history (two
false-positive rounds fixed) and current known limitations. Curved edges
(e.g. two arcs between the same node pair, each with its own weight and direction) are supported —
each qualifying curve produces its own `GraphEdge` entry in `edges`, so the same `node_a`/`node_b`
pair can legitimately appear twice.

**Errors:** `413` image too large; `422` malformed capture; `502` upstream model error (`error: "slide_analysis_failed"`, message is the friendly fallback text the sidebar shows per the UI guide's Error UX).

## 3. `POST /chat`

Ask a question grounded in a query mode. Response is Server-Sent Events, relayed by the backend from the Claude streaming call.

**Request:**
```
ChatRequest:
  conversation_id: str | null     # null → new conversation
  presentation_id: str | null     # required unless query_mode == "general"
  query_mode: "figure" | "slide" | "presentation" | "general" | "auto"
  slide_id: str | null            # required for "slide"/"figure"
  object_id: str | null           # required for "figure"
  message: str
```

**Response:** `text/event-stream`, events:
```
event: delta
data: { "text": "..." }

event: done
data: {
  "conversation_id": str,
  "message_id": str,
  "referenced_object_ids": [str],
  "usage": { "input_tokens": int, "output_tokens": int, "cache_read_input_tokens": int }
}

event: error
data: { "error": str, "message": str }
```

**Errors (pre-stream, `4xx` before any SSE bytes are sent):** `400` invalid mode/context combination (e.g. `figure` mode without `object_id`); `404` unknown `presentation_id`/`slide_id`/`object_id`.

## 4. `GET /presentations/{id}`

Fetch a presentation's indexing state and slide list — used by the sidebar's History/Presentation views.

**Response `200`:**
```
PresentationResponse:
  id: str
  title: str
  source_type: "live_capture" | "uploaded_deck"
  created_at: datetime
  slide_count: int
  slides: list[SlideSummary]

SlideSummary:
  id: str
  slide_number: int
  status: "pending" | "analyzed" | "failed"
  summary: str | null
  object_count: int
```

**Errors:** `404` unknown presentation.

## 5. `POST /quiz`

Generate quiz questions grounded in a slide or presentation.

**Request:**
```
QuizRequest:
  presentation_id: str
  scope: "slide" | "presentation"
  slide_id: str | null            # required if scope == "slide"
  question_count: int = 5
```

**Response `200`:**
```
QuizResponse:
  quiz_id: str
  questions: list[QuizQuestion]

QuizQuestion:
  id: str
  prompt: str
  choices: list[str] | null       # null for free-response
  answer: str
  explanation: str
  source_object_ids: list[str]
```

## 6. `POST /notes`

Generate structured notes/summary for a slide or presentation.

**Request:**
```
NotesRequest:
  presentation_id: str
  scope: "slide" | "presentation"
  slide_id: str | null
```

**Response `200`:**
```
NotesResponse:
  notes_id: str
  format: "markdown"
  content: str
  source_object_ids: list[str]
```

## 7. `GET /health`

Liveness/readiness check for the Docker Compose stack (DB, Redis, and — best-effort — Claude API reachability).

**Response `200`:**
```
HealthResponse:
  status: "ok" | "degraded"
  db: bool
  cache: bool
  model_provider: bool
```

## 8. Consistency with the Data Model

`SlideObject`, `SlideSummary`, `QuizQuestion.source_object_ids`, and `NotesResponse.source_object_ids` map directly onto the `objects` and `slides` tables in [DATA_MODEL.md](./DATA_MODEL.md) — no field here introduces a concept absent from that schema, and every entity name (`presentation`, `slide`, `object`, `conversation`, `message`) matches the table names exactly so the mapping between API and storage stays obvious as both evolve.
