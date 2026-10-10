"""Chat history for a signed-in user, plus the retention cleanup hook.

GET /conversations, GET /conversations/{id}, DELETE /conversations/{id}
need a session token: history belongs to an account, so there is nothing
to list for an anonymous request. Another user's chat, or an expired one,
is a 404, same as an unknown id.
"""

import uuid
from datetime import UTC

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id, verify_api_key
from app.core.config import get_settings
from app.db.session import get_db
from app.models.orm import Conversation
from app.models.schemas import (
    ConversationDetail,
    ConversationListResponse,
    ConversationMessage,
    ConversationSummary,
    SlideAnalysisResponse,
)
from app.repositories.conversations import ConversationRepository
from app.repositories.messages import MessageRepository
from app.repositories.objects import ObjectRepository
from app.repositories.slides import SlideRepository
from app.services.retention import retention_cutoff, run_cleanup

router = APIRouter(tags=["conversations"], dependencies=[Depends(verify_api_key)])


def _require_user(current_user_id: uuid.UUID | None) -> uuid.UUID:
    if current_user_id is None:
        raise HTTPException(status_code=401, detail="Sign in to see your recent chats.")
    return current_user_id


async def _get_owned(db: AsyncSession, conversation_id: str, user_id: uuid.UUID) -> Conversation:
    try:
        parsed = uuid.UUID(conversation_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Unknown conversation") from exc
    conversation = await ConversationRepository(db).get(parsed)
    if conversation is None or conversation.user_id != user_id:
        raise HTTPException(status_code=404, detail="Unknown conversation")
    last_activity = conversation.last_activity_at
    if last_activity.tzinfo is None:  # SQLite round-trip; every write is UTC
        last_activity = last_activity.replace(tzinfo=UTC)
    if last_activity < retention_cutoff():
        raise HTTPException(status_code=404, detail="Unknown conversation")
    return conversation


@router.get("/conversations", response_model=ConversationListResponse)
async def list_conversations(
    db: AsyncSession = Depends(get_db),
    current_user_id: uuid.UUID | None = Depends(get_current_user_id),
) -> ConversationListResponse:
    user_id = _require_user(current_user_id)
    conversations = await ConversationRepository(db).list_recent_for_user(user_id, retention_cutoff())
    return ConversationListResponse(
        retention_days=get_settings().chat_retention_days,
        conversations=[
            ConversationSummary(id=str(c.id), title=c.title or "Untitled chat", last_activity_at=c.last_activity_at)
            for c in conversations
        ],
    )


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user_id: uuid.UUID | None = Depends(get_current_user_id),
) -> ConversationDetail:
    conversation = await _get_owned(db, conversation_id, _require_user(current_user_id))

    slide_response = None
    slide = await SlideRepository(db).get(conversation.slide_id) if conversation.slide_id else None
    if slide is not None:
        objects = ObjectRepository(db)
        slide_response = SlideAnalysisResponse(
            presentation_id=slide.presentation_id,
            slide_id=slide.id,
            cache_hit=True,
            status=slide.status,
            objects=[objects.to_slide_object(record) for record in await objects.list_by_slide(slide.id)],
            summary=slide.summary or "",
        )

    messages = await MessageRepository(db).list_by_conversation(conversation.id)
    return ConversationDetail(
        id=str(conversation.id),
        title=conversation.title or "Untitled chat",
        slide=slide_response,
        messages=[
            ConversationMessage(id=str(m.id), role=m.role, content=m.content, created_at=m.created_at) for m in messages
        ],
    )


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user_id: uuid.UUID | None = Depends(get_current_user_id),
) -> None:
    conversation = await _get_owned(db, conversation_id, _require_user(current_user_id))
    await ConversationRepository(db).delete(conversation.id)
    await db.commit()


@router.post("/maintenance/cleanup")
async def cleanup(db: AsyncSession = Depends(get_db)) -> dict[str, int]:
    """Deletes everything past retention. Safe for any holder of the API
    key to call at any time: it only removes rows that have already expired."""
    return (await run_cleanup(db)).as_dict()
