"""POST /chat — docs/API_CONTRACT.md §3.

"figure", "slide", "algorithm", "tutor" and "general" query_mode values are
handled. "presentation" and "auto" need RetrievalService (M4) and are
rejected with 400 rather than silently degraded to something else.
"general" is an open chat with no slide behind it: no presentation, no
grounding data, just the tutor prompt and the conversation. "algorithm" grounds the
same way as "slide" (same objects, same slide_id requirement) but also
runs each object through recurrence_solver.py's deterministic Master
Theorem checker and injects any verified results into the context
(docs/AlgorithmsMVP.md Phase 2), on top of using an algorithms-aware
prompt.

Response is `text/event-stream` (SSE), not a JSON body — see
`_stream_response` for the exact event shapes, matching the contract:
`event: delta` (repeated), then either `event: done` or `event: error`.
"""

import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from app.api.deps import (
    ensure_presentation_access,
    enforce_chat_rate_limit,
    get_chat_service,
    get_current_user_id,
    resolve_chat_service,
    verify_api_key,
)
from app.core.prompt_loader import load_prompt
from app.db.session import get_db
from app.models.orm import ObjectRecord, Quiz, Series, Slide
from app.models.schemas import ChatRequest, ExplanationMode, GraphStructure
from app.repositories.conversations import ConversationRepository
from app.repositories.messages import MessageRepository
from app.repositories.objects import ObjectRepository
from app.repositories.presentations import PresentationRepository
from app.repositories.slides import SlideRepository
from app.repositories.usage_events import UsageEventRepository
from app.services.algorithm_tracer import find_algorithm_name, find_array, find_target, format_result
from app.services.algorithm_tracer import trace as trace_algorithm
from app.services.chat_service import ChatEffort, ChatService
from app.services.usage import estimate_cost_usd
from app.services.graph_algorithm_tracer import find_graph_algorithm, find_start_node
from app.services.graph_algorithm_tracer import trace as trace_graph_algorithm
from app.services.recurrence_solver import RecurrenceAnalysis, analyze_recurrence

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"], dependencies=[Depends(verify_api_key), Depends(enforce_chat_rate_limit)])

_PROMPT_BY_MODE = {
    "figure": "chat_figure.v5",
    "slide": "chat_slide.v5",
    "algorithm": "chat_algorithm.v5",
    "tutor": "chat_tutor.v1",
    "general": "chat_general.v1",
}
_EFFORT_BY_MODE: dict[str, ChatEffort] = {
    "figure": "low",
    "slide": "medium",
    "algorithm": "medium",
    "tutor": "medium",
    "general": "medium",
}

# docs/TheoryOfAlgorithm.md §24 / docs/AlgorithmsMVP.md Phase 5. "university"
# has no entry — it's what chat_algorithm.v4.md's baseline tone already is,
# so there's nothing to append and the prompt stays unchanged for the
# default case.
_EXPLANATION_MODE_INSTRUCTIONS: dict[str, str] = {
    "simple": (
        "Explain as if the student has never encountered this concept before. Skip formal "
        "notation wherever you can; the moment you must use a term or symbol, define it in "
        "plain language. Lead with a small concrete example or an everyday analogy before any "
        "general statement — intuition first, formalism only if it's actually needed."
    ),
    "rigorous": (
        "Give a rigorous treatment: formal definitions, complete derivations without skipping "
        "steps, explicit assumptions, and edge cases, on top of the usual complexity analysis. "
        "It's fine for the answer to be longer than usual here — thoroughness matters more than "
        "brevity in this mode."
    ),
    "exam": (
        "Optimize for exam prep: lead with what needs to be remembered and the general method "
        "for solving problems shaped like this one, flag common traps students fall into on this "
        "topic, and keep the explanation tight rather than exploratory. Skip background the "
        "question already implies the student has."
    ),
    "socratic": (
        "OVERRIDE — this rule takes precedence over every other instruction below, including "
        "'never state a complexity class without deriving it' and any instruction to walk through "
        "or present a derivation: do not give the final answer, a complexity class, or any part of "
        "a derivation in this turn, even though you already know it and would normally show your "
        "work in full. The point of this mode is the question, not the answer. Ask exactly one "
        "guiding question that leads the student to the next step themselves, phrased the way a "
        "good tutor would ask it, and stop there — one short question, nothing else, not even as a "
        "lead-in. If the conversation history shows the student has already made progress, build "
        "the next question on that instead of restarting from the beginning. Reveal the full "
        "answer only once the student has worked their way to it themselves, or explicitly asks "
        "you to just tell them — and even then, confirm what they got right first rather than only "
        "restating the answer yourself."
    ),
}


def _explanation_mode_prefix(mode: ExplanationMode) -> str:
    """Returns a block to PREPEND before the base algorithm prompt (not
    append after it) — a live test showed appending "socratic" mode's
    instruction after the base prompt's own "always fully derive, never
    skip a step" instructions wasn't enough; the model kept giving the
    full answer regardless of the block's wording or of whether a
    verified block was even present. Leading with the mode instruction
    and explicitly declaring it overrides the base prompt (see the
    "OVERRIDE" framing above) is what actually worked."""
    instruction = _EXPLANATION_MODE_INSTRUCTIONS.get(mode)
    return f"## Explanation mode: {mode}\n\n{instruction}\n\n" if instruction else ""


def _parse_uuid(value: str, field_name: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Malformed {field_name}") from exc


def _format_object(obj: ObjectRecord) -> str:
    lines = [f"- type: {obj.type}", f"  bounding_box: {obj.bounding_box}"]
    if obj.extracted_text:
        lines.append(f"  extracted_text: {obj.extracted_text}")
    if obj.latex:
        lines.append(f"  latex: {obj.latex}")
    if obj.language:
        lines.append(f"  language: {obj.language}")
    if obj.summary:
        lines.append(f"  summary: {obj.summary}")
    if obj.graph_structure:
        graph = GraphStructure(**obj.graph_structure)
        edges_desc = "; ".join(
            f"{e.node_a}--{e.node_b}" + (f" (weight {e.weight:g})" if e.weight is not None else "") + f" [{e.direction}]"
            for e in graph.edges
        ) or "(none)"
        lines.append(f"  graph_nodes: {', '.join(graph.nodes)}")
        lines.append(f"  graph_edges: {edges_desc}")
    return "\n".join(lines)


async def _get_slide(db: AsyncSession, request: ChatRequest, presentation_id: uuid.UUID, mode: str) -> Slide:
    """The slide being asked about. It must belong to the presentation the
    caller was just authorised for: otherwise naming your own presentation
    with someone else's slide id would put their slide in the model's context."""
    if not request.slide_id:
        raise HTTPException(status_code=400, detail=f"{mode} mode requires slide_id")
    slide = await SlideRepository(db).get(_parse_uuid(request.slide_id, "slide_id"))
    if slide is None or slide.presentation_id != presentation_id:
        raise HTTPException(status_code=404, detail="Unknown slide_id")
    return slide


# How many earlier messages (questions and answers together) a chat turn
# resends. Each turn pays for every earlier message again, so a very long
# conversation would cost more with every question; ten exchanges keep the
# thread of a tutoring conversation, and the slide itself is always in the
# system prompt whatever is left out here.
MAX_HISTORY_MESSAGES = 20


def recent_history(history: list[tuple[str, str]], limit: int = MAX_HISTORY_MESSAGES) -> list[tuple[str, str]]:
    """The last `limit` messages of a conversation, starting on a question:
    when the cut falls on an answer, that answer is dropped too, so the
    model never sees a reply without the question it answered."""
    recent = history[-limit:] if limit > 0 else []
    while recent and recent[0][0] != "user":
        recent = recent[1:]
    return recent


_SERIES_CONTEXT_SLIDES = 5
_PREVIOUS_SLIDE_TEXT_CHARS = 800


async def _build_series_block(db: AsyncSession, slide: Slide) -> str:
    """What the student captured earlier in the same series, so a question
    like "how does this follow from the last slide?" has something to stand
    on. Summaries only, plus the text of the slide just before this one."""
    if slide.series_id is None:
        return ""
    series = await db.get(Series, slide.series_id)
    earlier = list(
        (
            await db.execute(
                select(Slide)
                .where(Slide.series_id == slide.series_id, Slide.id != slide.id, Slide.created_at <= slide.created_at)
                .order_by(Slide.created_at.desc())
                .limit(_SERIES_CONTEXT_SLIDES)
            )
        ).scalars()
    )
    if series is None or not earlier:
        return ""

    lines = [f"- {f'[{s.subtopic}] ' if s.subtopic else ''}{s.summary or '(no summary)'}" for s in reversed(earlier)]
    previous_objects = await ObjectRepository(db).list_by_slide(earlier[0].id)
    previous_text = " ".join(o.extracted_text or o.latex or "" for o in previous_objects).strip()
    previous_block = (
        f"\n\nText of the slide captured just before this one:\n{previous_text[:_PREVIOUS_SLIDE_TEXT_CHARS]}"
        if previous_text
        else ""
    )
    return (
        f"\n\nThis slide is part of the student's series \"{series.title}\" ({series.category}). Earlier slides "
        "they captured in it, oldest first (background for continuity; the slide being asked about is the "
        "one above). Earlier turns of this conversation may have been about those slides, when one of them "
        "was the current slide; that is expected, so do not remark on it or correct it:\n"
        + "\n".join(lines)
        + previous_block
    )


async def _build_figure_context(
    db: AsyncSession, request: ChatRequest, presentation_id: uuid.UUID
) -> tuple[str, list[str]]:
    if not request.object_id or not request.slide_id:
        raise HTTPException(status_code=400, detail="Figure mode requires object_id and slide_id")

    slide = await _get_slide(db, request, presentation_id, "Figure")
    object_id = _parse_uuid(request.object_id, "object_id")
    obj = await ObjectRepository(db).get(object_id)
    if obj is None or obj.slide_id != slide.id:
        raise HTTPException(status_code=404, detail="Unknown object_id")

    context = f"<slide_data>\nSlide summary: {slide.summary or '(none)'}\n\nSelected figure:\n{_format_object(obj)}\n</slide_data>"
    return context, [str(obj.id)]


async def _build_slide_context(
    db: AsyncSession, request: ChatRequest, presentation_id: uuid.UUID
) -> tuple[str, list[str]]:
    slide = await _get_slide(db, request, presentation_id, "Slide")
    objects = await ObjectRepository(db).list_by_slide(slide.id)
    objects_text = "\n\n".join(_format_object(o) for o in objects) or "(no objects extracted)"
    series_block = await _build_series_block(db, slide)
    context = (
        f"<slide_data>\nSlide summary: {slide.summary or '(none)'}\n\n"
        f"Objects on this slide:\n{objects_text}{series_block}\n</slide_data>"
    )
    return context, [str(o.id) for o in objects]


def _format_recurrence_analysis(analysis: RecurrenceAnalysis) -> str:
    lines = [
        f"- recurrence: T(n) = {analysis.a:g}T(n/{analysis.b:g}) + {analysis.f_n}",
        f"  n^(log_b a) = {analysis.n_pow_log_b_a}",
        f"  Master Theorem case: {analysis.master_case}",
    ]
    if analysis.complexity:
        lines.append(f"  complexity: {analysis.complexity}")
    lines.append(f"  reasoning: {analysis.notes}")
    lines.append(f"  recursion tree:\n{analysis.recursion_tree}")
    return "\n".join(lines)


async def _build_algorithm_context(
    db: AsyncSession, request: ChatRequest, presentation_id: uuid.UUID
) -> tuple[str, list[str]]:
    """Same grounding as "slide" mode, plus a deterministically verified
    Master Theorem analysis (backend/app/services/recurrence_solver.py) for
    any recurrence found among the slide's objects — closes the
    verification gap flagged in docs/AlgorithmsMVP.md Phase 1, since the
    chat model's own complexity math is never the only source of truth for
    the recurrences this checker can handle."""
    slide = await _get_slide(db, request, presentation_id, "Algorithm")
    objects = await ObjectRepository(db).list_by_slide(slide.id)
    objects_text = "\n\n".join(_format_object(o) for o in objects) or "(no objects extracted)"

    analyses: list[RecurrenceAnalysis] = []
    for obj in objects:
        for candidate in (obj.latex, obj.extracted_text):
            if not candidate:
                continue
            analysis = analyze_recurrence(candidate)
            if analysis is not None:
                analyses.append(analysis)
                break

    socratic = request.explanation_mode == "socratic"

    # Socratic mode withholds the verified blocks entirely rather than
    # relabeling them "don't reveal" — tried in an earlier revision, but a
    # live test showed the model narrated the full derivation anyway once
    # the numeric answer was sitting in context, regardless of how the
    # section was labeled (see docs/AlgorithmsMVP.md Phase 5's socratic
    # mode note). Withholding the data itself is the only reliable fix;
    # the tradeoff is the socratic student doesn't get the verification
    # safety net this turn, which is an acceptable loss since socratic
    # mode's whole point is the model asking, not stating, math.
    recurrence_block = ""
    if analyses and not socratic:
        recurrence_block = (
            "\n\nVerified recurrence analysis (computed exactly by a symbolic solver, not by "
            "you — trust this over your own derivation of the same recurrence; if a case is "
            "marked 'inconclusive', derive that one yourself and say explicitly that it doesn't "
            "fit the standard Master Theorem shape):\n\n" + "\n\n".join(_format_recurrence_analysis(a) for a in analyses)
        )

    trace_block = "" if socratic else _build_trace_block(request.message, objects)
    graph_trace_block = "" if socratic else _build_graph_trace_block(request.message, objects)

    context = (
        f"<slide_data>\nSlide summary: {slide.summary or '(none)'}\n\n"
        f"Objects on this slide:\n{objects_text}{recurrence_block}{trace_block}{graph_trace_block}"
        f"{await _build_series_block(db, slide)}\n</slide_data>"
    )
    return context, [str(o.id) for o in objects]


def _build_trace_block(message: str, objects: list[ObjectRecord]) -> str:
    """Detects a sorting/searching-catalog request (docs/AlgorithmsMVP.md
    Phase 3) from the student's message and the slide's extracted text,
    and — if both an algorithm and an input array are found — returns a
    verified execution trace block (algorithm_tracer.py, which actually
    runs the algorithm rather than asking the model to simulate it), or
    "" if nothing was recognized."""
    slide_text = " ".join(
        text for obj in objects for text in (obj.extracted_text, obj.summary) if text
    )

    algorithm_key = find_algorithm_name(message) or find_algorithm_name(slide_text)
    array = find_array(message) or find_array(slide_text)
    if algorithm_key is None or array is None:
        return ""

    target = find_target(message)
    result = trace_algorithm(algorithm_key, array, target)
    if result is None:
        return ""

    return (
        "\n\nVerified algorithm trace (computed exactly by actually running the algorithm on "
        "this input, not by you simulating it — trust this over your own mental execution):\n\n"
        + "\n".join(result.steps)
        + f"\n\nresult: {format_result(result.result)}"
    )


def _build_graph_trace_block(message: str, objects: list[ObjectRecord]) -> str:
    """Detects a BFS/DFS traversal request (docs/AlgorithmsMVP.md Phase 4)
    against the first graph-shaped object on the slide (its
    `graph_structure`, already extracted by the hybrid VLM + CV pipeline —
    see ADR-010 — at slide-analyze time, not re-derived here), and — if
    the request is recognized — returns a verified traversal-order block
    (graph_algorithm_tracer.py, which actually runs the traversal), or ""
    if nothing was recognized."""
    graph_object = next((o for o in objects if o.graph_structure), None)
    if graph_object is None:
        return ""

    algorithm_key = find_graph_algorithm(message)
    if algorithm_key is None:
        return ""

    graph = ObjectRepository.to_slide_object(graph_object).graph_structure
    if graph is None or not graph.nodes:
        return ""

    start = find_start_node(message, graph.nodes)
    used_default_start = start is None
    if start is None:
        start = graph.nodes[0]

    result = trace_graph_algorithm(algorithm_key, graph.nodes, graph.edges, start)
    if result is None:
        return ""

    default_note = (
        f" (no start node named in the question — defaulted to {start}, the first node on the slide)"
        if used_default_start
        else ""
    )
    return (
        f"\n\nVerified graph traversal (computed exactly by actually running {algorithm_key.upper()} "
        f"on the slide's extracted graph structure, not by you simulating it){default_note}:\n\n"
        + "\n".join(result.steps)
    )


async def _build_tutor_context(
    db: AsyncSession, request: ChatRequest, current_user_id: uuid.UUID | None
) -> tuple[str, list[str], Slide | None]:
    """Grounds a tutoring chat on one quiz question: what was asked, what
    the student chose, what is correct, and the slide it was drawn from (when
    that slide still exists). The quiz must be the caller's own."""
    if not request.quiz_id or request.question_index is None:
        raise HTTPException(status_code=400, detail="Tutor mode requires quiz_id and question_index")
    quiz = await db.get(Quiz, _parse_uuid(request.quiz_id, "quiz_id"))
    if quiz is None or current_user_id is None or quiz.user_id != current_user_id:
        raise HTTPException(status_code=404, detail="Unknown quiz_id")
    if not 0 <= request.question_index < len(quiz.questions):
        raise HTTPException(status_code=400, detail="question_index is out of range")
    question = quiz.questions[request.question_index]
    options: list[str] = question["options"]
    correct: int = question["correct_index"]
    chosen = request.selected_index
    if chosen is not None and not 0 <= chosen < len(options):
        raise HTTPException(status_code=400, detail="selected_index is out of range")

    def letter(index: int) -> str:
        return f"{chr(ord('A') + index)}. {options[index]}"

    if chosen is None:
        chose = "The student skipped this question."
    else:
        chose = f"The student chose: {letter(chosen)} ({'correct' if chosen == correct else 'incorrect'})"
    lines = [
        f"Question: {question['question']}",
        "Options:\n" + "\n".join(letter(i) for i in range(len(options))),
        chose,
        f"Correct option: {letter(correct)}",
        f"Quiz explanation: {question['explanation']}",
    ]

    slide = await db.get(Slide, uuid.UUID(question["slide_id"])) if question.get("slide_id") else None
    referenced: list[str] = []
    if slide is not None:
        objects = await ObjectRepository(db).list_by_slide(slide.id)
        referenced = [str(o.id) for o in objects]
        objects_text = "\n\n".join(_format_object(o) for o in objects) or "(no objects extracted)"
        lines.append(
            f"Slide the question was drawn from:\nSlide summary: {slide.summary or '(none)'}\n\n{objects_text}"
        )
    return "<quiz_data>\n" + "\n\n".join(lines) + "\n</quiz_data>", referenced, slide


async def _same_series(
    db: AsyncSession, first: uuid.UUID | None, second: uuid.UUID | None, user_id: uuid.UUID | None
) -> bool:
    """Both slides are in one series, and it belongs to this user."""
    if first is None or second is None or user_id is None:
        return False
    slides = SlideRepository(db)
    a, b = await slides.get(first), await slides.get(second)
    if a is None or b is None or a.series_id is None or a.series_id != b.series_id:
        return False
    series = await db.get(Series, a.series_id)
    return series is not None and series.user_id == user_id


async def _resolve_conversation(
    db: AsyncSession,
    request: ChatRequest,
    presentation_id: uuid.UUID | None,
    slide_id: uuid.UUID | None,
    current_user_id: uuid.UUID | None,
) -> uuid.UUID:
    conversations = ConversationRepository(db)
    if request.conversation_id:
        conversation_uuid = _parse_uuid(request.conversation_id, "conversation_id")
        conversation = await conversations.get(conversation_uuid)
        # A chat from another account, or about something unrelated, is
        # reported as unknown: its messages become model context, so
        # continuing it would leak them.
        if conversation is None or (conversation.user_id is not None and conversation.user_id != current_user_id):
            raise HTTPException(status_code=404, detail="Unknown conversation_id")
        if conversation.presentation_id != presentation_id:
            # A different page is fine when the student moved on to the next
            # slide of the same series: the chat follows them there.
            if not await _same_series(db, conversation.slide_id, slide_id, current_user_id):
                raise HTTPException(status_code=404, detail="Unknown conversation_id")
            conversation.presentation_id = presentation_id
        if slide_id is not None:
            conversation.slide_id = slide_id
        conversation.last_activity_at = datetime.now(UTC)
        return conversation.id
    conversation = await conversations.create(
        presentation_id=presentation_id,
        user_id=current_user_id,
        title=request.message.strip()[:80] or None,
        slide_id=slide_id,
    )
    return conversation.id


async def _stream_response(
    chat_service: ChatService,
    db: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    query_mode: str,
    system_prompt: str,
    message: str,
    effort: ChatEffort,
    referenced_object_ids: list[str],
    user_id: uuid.UUID | None,
) -> AsyncIterator[str]:
    start = time.perf_counter()
    full_text = ""
    try:
        messages = MessageRepository(db)
        # Fetched before this turn's user message is persisted, so it's
        # exactly the prior turns — this message is passed separately below.
        prior_messages = await messages.list_by_conversation(conversation_id)
        history = recent_history([(m.role, m.content) for m in prior_messages])

        await messages.create(
            conversation_id=conversation_id,
            role="user",
            content=message,
            query_mode=query_mode,
            referenced_object_ids=referenced_object_ids,
        )

        async for chunk in chat_service.stream_chat(
            system_prompt=system_prompt, message=message, effort=effort, history=history
        ):
            if chunk.delta:
                full_text += chunk.delta
                yield f"event: delta\ndata: {json.dumps({'text': chunk.delta})}\n\n"
            if chunk.done and chunk.usage is not None:
                assistant_message = await messages.create(
                    conversation_id=conversation_id,
                    role="assistant",
                    content=full_text,
                    query_mode=query_mode,
                    referenced_object_ids=referenced_object_ids,
                )
                await UsageEventRepository(db).record(
                    user_id=user_id,
                    action="chat",
                    model=chat_service.model_name,
                    input_tokens=chunk.usage.input_tokens,
                    output_tokens=chunk.usage.output_tokens,
                    est_cost_usd=estimate_cost_usd(
                        chat_service.model_name,
                        chunk.usage.input_tokens,
                        chunk.usage.output_tokens,
                        cache_creation_input_tokens=chunk.usage.cache_creation_input_tokens,
                        cache_read_input_tokens=chunk.usage.cache_read_input_tokens,
                    ),
                    conversation_id=conversation_id,
                )
                await db.commit()

                elapsed_ms = int((time.perf_counter() - start) * 1000)
                logger.info(
                    "chat_complete query_mode=%s model_used=%s cache_read_input_tokens=%d elapsed_ms=%d",
                    query_mode,
                    chat_service.model_name,
                    chunk.usage.cache_read_input_tokens,
                    elapsed_ms,
                )

                done_payload = {
                    "conversation_id": str(conversation_id),
                    "message_id": str(assistant_message.id),
                    "referenced_object_ids": referenced_object_ids,
                    "usage": chunk.usage.model_dump(),
                }
                yield f"event: done\ndata: {json.dumps(done_payload)}\n\n"
    except Exception:
        # A raise here can't change the HTTP status (headers/body have
        # already started streaming) — an `error` SSE event is this
        # endpoint's equivalent of "never crash the sidebar"
        # (docs/ARCHITECTURE.md §6) for a stream instead of a request.
        logger.warning("chat_stream_failed query_mode=%s", query_mode, exc_info=True)
        error_payload = {"error": "chat_stream_failed", "message": "The chat response could not be completed."}
        yield f"event: error\ndata: {json.dumps(error_payload)}\n\n"


@router.post("/chat")
async def chat(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db),
    chat_service: ChatService | None = Depends(get_chat_service),
    current_user_id: uuid.UUID | None = Depends(get_current_user_id),
) -> StreamingResponse:
    if chat_service is None:
        raise HTTPException(status_code=503, detail="Chat is not configured (no provider API key set)")
    chat_service = resolve_chat_service(chat_service, request.model)

    if request.query_mode not in _PROMPT_BY_MODE:
        raise HTTPException(status_code=400, detail=f"query_mode '{request.query_mode}' is not yet supported")

    presentation_uuid: uuid.UUID | None
    slide_uuid: uuid.UUID | None
    if request.query_mode == "tutor":
        # Grounded on a quiz the caller owns, not on a presentation they name.
        context_text, referenced_object_ids, quiz_slide = await _build_tutor_context(db, request, current_user_id)
        presentation_uuid = quiz_slide.presentation_id if quiz_slide is not None else None
        slide_uuid = quiz_slide.id if quiz_slide is not None else None
    elif request.query_mode == "general":
        # An open chat: nothing is looked up, so there is nothing of anyone's to guard.
        context_text, referenced_object_ids = "", []
        presentation_uuid = slide_uuid = None
    else:
        if not request.presentation_id:
            raise HTTPException(status_code=400, detail="presentation_id is required")
        presentation_uuid = _parse_uuid(request.presentation_id, "presentation_id")
        presentation = await PresentationRepository(db).get(presentation_uuid)
        if presentation is None:
            raise HTTPException(status_code=404, detail="Unknown presentation_id")
        ensure_presentation_access(presentation, current_user_id)

        if request.query_mode == "figure":
            context_text, referenced_object_ids = await _build_figure_context(db, request, presentation_uuid)
        elif request.query_mode == "algorithm":
            context_text, referenced_object_ids = await _build_algorithm_context(db, request, presentation_uuid)
        else:
            context_text, referenced_object_ids = await _build_slide_context(db, request, presentation_uuid)
        slide_uuid = _parse_uuid(request.slide_id, "slide_id") if request.slide_id else None

    conversation_id = await _resolve_conversation(db, request, presentation_uuid, slide_uuid, current_user_id)
    await db.commit()

    base_prompt = load_prompt(_PROMPT_BY_MODE[request.query_mode])
    explanation_mode_prefix = ""
    if request.query_mode == "algorithm":
        explanation_mode_prefix = _explanation_mode_prefix(request.explanation_mode)
    system_prompt = f"{explanation_mode_prefix}{base_prompt}\n\n{context_text}".rstrip()
    effort = _EFFORT_BY_MODE[request.query_mode]

    return StreamingResponse(
        _stream_response(
            chat_service,
            db,
            conversation_id=conversation_id,
            query_mode=request.query_mode,
            system_prompt=system_prompt,
            message=request.message,
            effort=effort,
            referenced_object_ids=referenced_object_ids,
            user_id=current_user_id,
        ),
        media_type="text/event-stream",
    )
