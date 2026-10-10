"""Repository for the `conversations` table (docs/DATA_MODEL.md §3)."""

import uuid
from datetime import datetime

from sqlalchemy import delete, exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orm import Conversation, Message


class ConversationRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get(self, conversation_id: uuid.UUID) -> Conversation | None:
        result = await self._db.execute(select(Conversation).where(Conversation.id == conversation_id))
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        presentation_id: uuid.UUID | None,
        user_id: uuid.UUID | None = None,
        title: str | None = None,
        slide_id: uuid.UUID | None = None,
    ) -> Conversation:
        conversation = Conversation(presentation_id=presentation_id, user_id=user_id, title=title, slide_id=slide_id)
        self._db.add(conversation)
        await self._db.flush()
        return conversation

    async def list_recent_for_user(self, user_id: uuid.UUID, since: datetime) -> list[Conversation]:
        """Newest first. Skips chats with no saved messages (a turn that was
        stopped or failed before its first answer leaves an empty thread)."""
        result = await self._db.execute(
            select(Conversation)
            .where(
                Conversation.user_id == user_id,
                Conversation.last_activity_at >= since,
                exists().where(Message.conversation_id == Conversation.id),
            )
            .order_by(Conversation.last_activity_at.desc())
        )
        return list(result.scalars().all())

    async def delete(self, conversation_id: uuid.UUID) -> None:
        await self._db.execute(delete(Message).where(Message.conversation_id == conversation_id))
        await self._db.execute(delete(Conversation).where(Conversation.id == conversation_id))
