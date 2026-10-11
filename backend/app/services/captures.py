"""What the capture lists (by lecture, by series) share."""

import uuid
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orm import Conversation, Message
from app.models.schemas import CaptureConversation

SUMMARY_PREVIEW_CHARS = 400


async def conversations_by_slide(
    db: AsyncSession, user_id: uuid.UUID, slide_ids: Sequence[uuid.UUID], since: datetime
) -> dict[uuid.UUID, list[CaptureConversation]]:
    """The user's unexpired chats about each slide, most recently active first."""
    chats: dict[uuid.UUID, list[CaptureConversation]] = defaultdict(list)
    if not slide_ids:
        return chats
    rows = (
        await db.execute(
            select(
                Conversation.id,
                Conversation.title,
                Conversation.slide_id,
                Conversation.last_activity_at,
                func.count(Message.id),
            )
            .join(Message, Message.conversation_id == Conversation.id)
            .where(
                Conversation.user_id == user_id,
                Conversation.slide_id.in_(slide_ids),
                Conversation.last_activity_at >= since,
            )
            .group_by(Conversation.id)
            .order_by(Conversation.last_activity_at.desc())
        )
    ).all()
    for conversation_id, title, slide_id, last_activity_at, message_count in rows:
        chats[slide_id].append(
            CaptureConversation(
                id=str(conversation_id),
                title=title or "Untitled chat",
                message_count=message_count,
                last_activity_at=last_activity_at,
            )
        )
    return chats
