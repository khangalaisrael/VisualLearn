"""Pydantic request/response schemas.

Mirrors docs/API_CONTRACT.md exactly for the two endpoints implemented in
Sprint 1 (`GET /health`, `POST /slides/analyze`). This file is the
authoritative source of truth for the extension's hand-written TypeScript
mirror in shared/types.ts — keep them in sync when this changes.

Note: `image_hash` is intentionally not part of `SlideAnalysisResponse`'s
input — see docs/API_CONTRACT.md §2 for why the backend derives it from the
uploaded bytes instead of trusting a client-supplied value.
"""

from datetime import datetime
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


ContentKind = Literal["lecture", "practice"]


class SeriesRef(BaseModel):
    """Where the sorter filed one capture (services/series.py)."""

    id: str
    category: str
    title: str
    # The specific aspect this one slide covers, narrower than the series title.
    subtopic: str | None = None
    kind: ContentKind = "lecture"


class SlideAnalysisResponse(BaseModel):
    presentation_id: UUID
    slide_id: UUID
    cache_hit: bool
    status: Literal["analyzed", "pending", "failed"]
    objects: list[SlideObject]
    summary: str
    # Null for a signed-out capture, or one the sorter could not place.
    series: SeriesRef | None = None


class AdminDay(BaseModel):
    date: str  # local calendar day, YYYY-MM-DD
    captures: int = 0
    chats: int = 0
    cost_usd: float = 0.0
    limit_hits: int = 0


class AdminOverview(BaseModel):
    generated_at: datetime
    timezone: str
    global_captures_today: int
    global_cap: int
    cost_today_usd: float
    cost_month_usd: float
    cost_30d_usd: float
    active_users_today: int
    total_users: int
    limit_hits_today: int
    waitlist_clicks: int
    waitlist_users: int
    days: list[AdminDay]


class AdminUser(BaseModel):
    user_id: str | None  # None = signed out / deleted accounts, pooled
    email: str | None
    captures_30d: int = 0
    chats_30d: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_30d_usd: float = 0.0
    limit_hits_30d: int = 0
    last_active: datetime | None = None
    is_outlier: bool = False
    is_admin: bool = False


class AdminUsersResponse(BaseModel):
    median_cost_usd: float
    users: list[AdminUser]


class AdminWaitlistEntry(BaseModel):
    email: str | None
    clicks: int
    first_click: datetime
    last_click: datetime
    sources: list[str]


class AdminWaitlistResponse(BaseModel):
    unique_users: int
    total_clicks: int
    entries: list[AdminWaitlistEntry]


class CaptureConversation(BaseModel):
    id: str
    title: str
    message_count: int
    last_activity_at: datetime


class CaptureSummary(BaseModel):
    slide_id: str
    slide_number: int
    summary: str
    created_at: datetime
    conversations: list[CaptureConversation]


class LectureSummary(BaseModel):
    id: str
    title: str
    page_url: str | None
    last_activity_at: datetime
    captures: list[CaptureSummary]


class LectureListResponse(BaseModel):
    retention_days: int
    lectures: list[LectureSummary]


class SeriesCapture(BaseModel):
    slide_id: str
    summary: str
    subtopic: str | None
    kind: ContentKind
    created_at: datetime
    # The page the capture was taken from.
    page_title: str
    page_url: str | None
    conversations: list[CaptureConversation]


class SeriesSummary(BaseModel):
    id: str
    category: str
    title: str
    cover_slide_id: str | None
    last_activity_at: datetime
    captures: list[SeriesCapture]  # newest first


class SeriesListResponse(BaseModel):
    retention_days: int
    series: list[SeriesSummary]  # most recently active first
    # Captures the sorter has not placed yet.
    unsorted: list[SeriesCapture]


class SeriesUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    category: str | None = Field(default=None, min_length=1, max_length=80)
    cover_slide_id: str | None = None


class ResortRequest(BaseModel):
    """Sort the captures the user already has again, a few per request.
    `offset` is where the previous request stopped (0 to start)."""

    offset: int = Field(default=0, ge=0)


class ResortResponse(BaseModel):
    # How many captures the pass has been through, out of `total`.
    processed: int
    total: int
    done: bool


class MoveSlideRequest(BaseModel):
    """Move a capture to an existing series (`series_id`) or to a new one
    (`category` and `title`)."""

    series_id: str | None = None
    category: str | None = Field(default=None, min_length=1, max_length=80)
    title: str | None = Field(default=None, min_length=1, max_length=120)


class NoteOut(BaseModel):
    id: str
    title: str
    body: str
    source: Literal["ai", "user"]
    # The series the note is filed under, by its current name; when that
    # series is gone, the name it had when the note was made.
    topic: str | None
    # That series' category; null when the note has no series or the series is gone.
    category: str | None = None
    # Marked as a favourite by its owner.
    starred: bool = False
    series_id: str | None
    slide_id: str | None
    created_at: datetime
    updated_at: datetime


class NoteListResponse(BaseModel):
    notes: list[NoteOut]  # most recently edited first


class NoteCreateRequest(BaseModel):
    title: str = Field(default="", max_length=200)
    body: str = Field(min_length=1, max_length=20_000)
    source: Literal["ai", "user"] = "user"
    # Either may be given; a slide's series is used when only the slide is.
    series_id: str | None = None
    slide_id: str | None = None


class NoteUpdateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    body: str | None = Field(default=None, min_length=1, max_length=20_000)
    starred: bool | None = None


class QuizQuestion(BaseModel):
    question: str
    options: list[str]
    correct_index: int
    explanation: str
    # The slide the question draws on; null if none was named or it is gone.
    slide_id: str | None = None


class QuizResource(BaseModel):
    title: str
    url: str
    # One line on what it is good for.
    why: str


class QuizSummary(BaseModel):
    id: str
    title: str
    question_count: int
    created_at: datetime
    attempts: int
    best_score: int | None


class QuizOut(QuizSummary):
    series_id: str
    questions: list[QuizQuestion]
    resources: list[QuizResource]


class QuizListResponse(BaseModel):
    quizzes: list[QuizSummary]  # newest first


class QuizCreateRequest(BaseModel):
    count: int = Field(default=5, ge=3, le=20)
    # Also search the web for study resources on the topic. Admins only for now.
    research: bool = False


class QuizAttemptRequest(BaseModel):
    # The chosen option per question, in order; null for a skipped one.
    answers: list[int | None]


class QuizAttemptResponse(BaseModel):
    score: int
    total: int


StudyAidKind = Literal["guide", "cheatsheet", "flashcards"]


class Flashcard(BaseModel):
    front: str
    back: str


class StudyAidSummary(BaseModel):
    id: str
    kind: StudyAidKind
    title: str
    created_at: datetime
    # Flashcards only: how many cards, and how many the student marked as known.
    card_count: int | None = None
    known_count: int | None = None
    # How many slides it was written from; null when that was not recorded
    # (an aid from before it was, written from at most the newest 12).
    slide_count: int | None = None


class StudyAidOut(StudyAidSummary):
    series_id: str
    # The guide or cheat sheet text; null for flashcards.
    markdown: str | None = None
    # The deck; null for the two documents.
    cards: list[Flashcard] | None = None
    # Positions (from 0) of the cards marked as known.
    known: list[int] = []


class StudyAidListResponse(BaseModel):
    aids: list[StudyAidSummary]
    # How many slides an aid written now would be written from: more than an
    # aid's own `slide_count` means the series has grown past it.
    series_slide_count: int = 0


class StudyAidCreateRequest(BaseModel):
    kind: StudyAidKind


CodeLanguage = Literal["haskell", "java", "cpp", "python"]


class CodeRunRequest(BaseModel):
    language: CodeLanguage
    code: str = Field(max_length=20_000)
    # What the program reads from standard input.
    stdin: str = Field(default="", max_length=10_000)
    # Haskell and Python only: expressions to evaluate after the code, one per
    # line, as they would be typed in GHCi or the Python shell.
    expressions: str = Field(default="", max_length=4_000)


class CodeRunResponse(BaseModel):
    # "timeout": the program ran too long and was stopped.
    status: Literal["ok", "compile_error", "runtime_error", "timeout"]
    stdout: str
    stderr: str
    # The compiler's errors and warnings.
    compiler_output: str
    duration_ms: int


class CodeFixRequest(BaseModel):
    """Make this code a complete program that runs. `last_run` is what the
    last run reported (compiler errors, a crash), when there was one."""

    language: CodeLanguage
    code: str = Field(max_length=20_000)
    stdin: str = Field(default="", max_length=10_000)
    last_run: str = Field(default="", max_length=20_000)


class CodeFixResponse(BaseModel):
    code: str
    # What was added or changed, in a sentence or two.
    note: str


class StudyAidProgressRequest(BaseModel):
    known: list[int]


QueryMode = Literal["figure", "slide", "algorithm", "tutor", "presentation", "general", "auto"]

# docs/TheoryOfAlgorithm.md §24 / docs/AlgorithmsMVP.md Phase 5. Only
# consulted for query_mode == "algorithm" (see chat.py's
# _EXPLANATION_MODE_INSTRUCTIONS) — other modes ignore this field.
ExplanationMode = Literal["simple", "university", "rigorous", "exam", "socratic"]


class ChatRequest(BaseModel):
    """POST /chat request body (docs/API_CONTRACT.md §3). "figure", "slide",
    "algorithm", "tutor" and "general" query_mode values are handled.
    "presentation" and "auto" arrive with M4's RetrievalService; the router
    rejects those two with 400 for now. "general" is an open chat with no
    slide: it needs only `message`. "algorithm" grounds on the same objects as "slide" (same
    slide_id requirement) but also runs a deterministic Master Theorem
    check on any recurrence found and uses an algorithms-aware prompt
    (docs/AlgorithmsMVP.md Phase 1 & 2)."""

    conversation_id: str | None = None
    presentation_id: str | None = None
    query_mode: QueryMode
    slide_id: str | None = None
    object_id: str | None = None
    message: str
    # Optional per-request model override (gpt-4o / gpt-4o-mini on an
    # OpenAI backend, claude-haiku-5-5 / claude-sonnet-5-5 on an Anthropic
    # one), set from the extension's Settings tab. None keeps the
    # server-configured default (app/api/deps.py's resolve_chat_service).
    model: str | None = None
    # Only used for query_mode == "algorithm" (docs/AlgorithmsMVP.md
    # Phase 5) — ignored otherwise, so other modes don't need to send it.
    explanation_mode: ExplanationMode = "university"
    # Only for query_mode == "tutor": the quiz question being discussed and
    # the option the student chose (null if they skipped it).
    quiz_id: str | None = None
    question_index: int | None = None
    selected_index: int | None = None


class ChatUsage(BaseModel):
    input_tokens: int
    output_tokens: int
    # OpenAI's streaming API doesn't report a prompt-cache-read figure the
    # way Anthropic's usage block does; OpenAIChatService always reports 0
    # here rather than omitting the field (docs/API_CONTRACT.md §3 always
    # includes it in the `done` event).
    cache_read_input_tokens: int = 0
    # Tokens written to the prompt cache on this turn (Anthropic only, 0 for
    # OpenAI). Like cache reads, they are not part of `input_tokens`.
    cache_creation_input_tokens: int = 0


class ErrorResponse(BaseModel):
    error: str
    message: str
    request_id: str


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    db: bool
    cache: bool
    model_provider: bool


class GoogleAuthRequest(BaseModel):
    """POST /auth/google request body. `access_token` is what the extension
    gets back from `chrome.identity.getAuthToken` — an OAuth access token
    valid for calling Google's own APIs, not a signed ID token — so the
    backend verifies it by calling Google's userinfo endpoint with it
    (app/services/google_oauth.py), rather than verifying a JWT signature
    locally."""

    access_token: str


class AuthResponse(BaseModel):
    session_token: str
    email: str | None = None


class LogoutRequest(BaseModel):
    session_token: str


class ConversationSummary(BaseModel):
    id: str
    title: str
    last_activity_at: datetime


class ConversationListResponse(BaseModel):
    # How long chats are kept, so the UI states the real number.
    retention_days: int
    conversations: list[ConversationSummary]


class ConversationMessage(BaseModel):
    id: str
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime


class ConversationDetail(BaseModel):
    id: str
    title: str
    # The slide the chat is about; null if that slide no longer exists.
    slide: SlideAnalysisResponse | None
    messages: list[ConversationMessage]


class UsageWindow(BaseModel):
    used: int
    limit: int
    # When this window next resets (UTC). The extension turns it into
    # "resets in 6h 12m" and "resets on the 1st".
    resets_at: datetime


class UsageResponse(BaseModel):
    signed_in: bool
    is_admin: bool
    unlimited: bool
    captures_today: UsageWindow
    captures_month: UsageWindow
    chat_today: UsageWindow
    # The global daily capacity cap is reached (not this user's own limit).
    global_blocked: bool
    # Invite-only mode: `allowed` is False for anyone not on the list (signed out included).
    invite_only: bool = False
    allowed: bool = True
    invite_contact: str | None = None


class WaitlistRequest(BaseModel):
    source: Literal["daily", "monthly", "settings"]


class WaitlistResponse(BaseModel):
    joined: bool
