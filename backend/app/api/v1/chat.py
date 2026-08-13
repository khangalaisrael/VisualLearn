"""POST /chat — docs/API_CONTRACT.md §3.

Milestone 3 scope: only "figure" and "slide" query_mode values are
handled. "presentation" and "auto" need RetrievalService (M4); "general"
has no grounding story yet — all three are rejected with 400 rather than
silently degraded to something else.

Response is `text/event-stream` (SSE), not a JSON body — see
`_stream_response` for the exact event shapes, matching the contract:
`event: delta` (repeated), then either `event: done` or `event: error`.
"""

import json
import logging
import time
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from app.api.deps import get_chat_service, verify_api_key
from app.core.prompt_loader import load_prompt
from app.db.session import get_db
from app.models.orm import ObjectRecord
from app.models.schemas import ChatRequest
from app.repositories.conversations import ConversationRepository
from app.repositories.messages import MessageRepository
from app.repositories.objects import ObjectRepository
from app.repositories.presentations import PresentationRepository
from app.repositories.slides import SlideRepository
from app.services.chat_service import ChatEffort, ChatService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"], dependencies=[Depends(verify_api_key)])

_PROMPT_BY_MODE = {"figure": "chat_figure.v3", "slide": "chat_slide.v3"}
_EFFORT_BY_MODE: dict[str, ChatEffort] = {"figure": "low", "slide": "medium"}


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
    if obj.summary:
        lines.append(f"  summary: {obj.summary}")
    return "\n".join(lines)


async def _build_figure_context(db: AsyncSession, request: ChatRequest) -> tuple[str, list[str]]:
    if not request.object_id or not request.slide_id:
        raise HTTPException(status_code=400, detail="Figure mode requires object_id and slide_id")

    object_id = _parse_uuid(request.object_id, "object_id")
    obj = await ObjectRepository(db).get(object_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Unknown object_id")

    slide_id = _parse_uuid(request.slide_id, "slide_id")
    slide = await SlideRepository(db).get(slide_id)
    if slide is None:
        raise HTTPException(status_code=404, detail="Unknown slide_id")

    context = f"<slide_data>\nSlide summary: {slide.summary or '(none)'}\n\nSelected figure:\n{_format_object(obj)}\n</slide_data>"
    return context, [str(obj.id)]


async def _build_slide_context(db: AsyncSession, request: ChatRequest) -> tuple[str, list[str]]:
    if not request.slide_id:
        raise HTTPException(status_code=400, detail="Slide mode requires slide_id")

    slide_id = _parse_uuid(request.slide_id, "slide_id")
    slide = await SlideRepository(db).get(slide_id)
    if slide is None:
        raise HTTPException(status_code=404, detail="Unknown slide_id")

    objects = await ObjectRepository(db).list_by_slide(slide_id)
    objects_text = "\n\n".join(_format_object(o) for o in objects) or "(no objects extracted)"
    context = f"<slide_data>\nSlide summary: {slide.summary or '(none)'}\n\nObjects on this slide:\n{objects_text}\n</slide_data>"
    return context, [str(o.id) for o in objects]


async def _resolve_conversation(db: AsyncSession, request: ChatRequest, presentation_id: uuid.UUID) -> uuid.UUID:
    conversations = ConversationRepository(db)
    if request.conversation_id:
        conversation_uuid = _parse_uuid(request.conversation_id, "conversation_id")
        conversation = await conversations.get(conversation_uuid)
        if conversation is None:
            raise HTTPException(status_code=404, detail="Unknown conversation_id")
        return conversation.id
    conversation = await conversations.create(presentation_id=presentation_id)
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
) -> AsyncIterator[str]:
    start = time.perf_counter()
    full_text = ""
    try:
        messages = MessageRepository(db)
        await messages.create(
            conversation_id=conversation_id,
            role="user",
            content=message,
            query_mode=query_mode,
            referenced_object_ids=referenced_object_ids,
        )

        async for chunk in chat_service.stream_chat(system_prompt=system_prompt, message=message, effort=effort):
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
) -> StreamingResponse:
    if chat_service is None:
        raise HTTPException(status_code=503, detail="Chat is not configured (no provider API key set)")

    if request.query_mode not in _PROMPT_BY_MODE:
        raise HTTPException(status_code=400, detail=f"query_mode '{request.query_mode}' is not yet supported")

    if not request.presentation_id:
        raise HTTPException(status_code=400, detail="presentation_id is required")
    presentation_uuid = _parse_uuid(request.presentation_id, "presentation_id")
    presentation = await PresentationRepository(db).get(presentation_uuid)
    if presentation is None:
        raise HTTPException(status_code=404, detail="Unknown presentation_id")

    if request.query_mode == "figure":
        context_text, referenced_object_ids = await _build_figure_context(db, request)
    else:
        context_text, referenced_object_ids = await _build_slide_context(db, request)

    conversation_id = await _resolve_conversation(db, request, presentation_uuid)
    await db.commit()

    system_prompt = f"{load_prompt(_PROMPT_BY_MODE[request.query_mode])}\n\n{context_text}"
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
        ),
        media_type="text/event-stream",
    )
