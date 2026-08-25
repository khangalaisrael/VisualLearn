"""Pydantic request/response schemas.

Mirrors docs/API_CONTRACT.md exactly for the two endpoints implemented in
Sprint 1 (`GET /health`, `POST /slides/analyze`). This file is the
authoritative source of truth for the extension's hand-written TypeScript
mirror in shared/types.ts — keep them in sync when this changes.

Note: `image_hash` is intentionally not part of `SlideAnalysisResponse`'s
input — see docs/API_CONTRACT.md §2 for why the backend derives it from the
uploaded bytes instead of trusting a client-supplied value.
"""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

ObjectType = Literal["title", "paragraph", "equation", "diagram", "graph", "table", "image", "code"]


class BoundingBox(BaseModel):
    x: float
    y: float
    width: float
    height: float


EdgeDirection = Literal["a_to_b", "b_to_a", "bidirectional", "undirected"]


class GraphEdge(BaseModel):
    node_a: str
    node_b: str
    weight: float | None = None
    # "a_to_b"/"b_to_a": an arrowhead was detected at one end (classical CV,
    # not the VLM — see graph_topology.py's arrowhead-density heuristic).
    # "bidirectional": an arrowhead at both ends. "undirected": no
    # arrowhead at either end (a plain line/curve).
    direction: EdgeDirection = "undirected"


class GraphStructure(BaseModel):
    """Structured node/edge topology for graph-shaped diagrams.

    Populated by a hybrid VLM + classical computer-vision pipeline (see
    docs/adr/ADR-010-hybrid-graph-structure-extraction.md), not by the
    vision model alone — pure VLM line-tracing was measured at ~50-75%
    edge-attribution accuracy on graphs with crossing edges; the CV step
    (backend/app/services/graph_topology.py) tests connectivity directly by
    pixel-sampling between candidate node positions instead of asking a
    vision model to visually trace which line goes where.
    """

    nodes: list[str]
    edges: list[GraphEdge]


class SlideObject(BaseModel):
    id: str
    type: ObjectType
    bounding_box: BoundingBox
    extracted_text: str | None = None
    latex: str | None = None
    # Only for "code" objects (the programming language, e.g. "python"),
    # null otherwise — same "only for its own type" pattern as `latex`.
    language: str | None = None
    summary: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    graph_structure: GraphStructure | None = None


class SlideAnalysisResponse(BaseModel):
    presentation_id: UUID
    slide_id: UUID
    cache_hit: bool
    status: Literal["analyzed", "pending", "failed"]
    objects: list[SlideObject]
    summary: str


QueryMode = Literal["figure", "slide", "presentation", "general", "auto"]


class ChatRequest(BaseModel):
    """POST /chat request body (docs/API_CONTRACT.md §3). Only "figure" and
    "slide" query_mode values are handled as of Milestone 3 — "presentation"
    and "auto" arrive with M4's RetrievalService, "general" has no grounding
    story yet; the router rejects all three with 400 for now."""

    conversation_id: str | None = None
    presentation_id: str | None = None
    query_mode: QueryMode
    slide_id: str | None = None
    object_id: str | None = None
    message: str
    # Optional per-request override of the active OpenAI model (gpt-4o /
    # gpt-4o-mini), set from the extension's Settings tab. None keeps the
    # server-configured default (app/api/deps.py's resolve_chat_service).
    model: str | None = None


class ChatUsage(BaseModel):
    input_tokens: int
    output_tokens: int
    # OpenAI's streaming API doesn't report a prompt-cache-read figure the
    # way Anthropic's usage block does; OpenAIChatService always reports 0
    # here rather than omitting the field (docs/API_CONTRACT.md §3 always
    # includes it in the `done` event).
    cache_read_input_tokens: int = 0


class ErrorResponse(BaseModel):
    error: str
    message: str
    request_id: str


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    db: bool
    cache: bool
    model_provider: bool
