"""Repository for the `conversations` table (docs/DATA_MODEL.md §3)."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orm import Conversation


class ConversationRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get(self, conversation_id: uuid.UUID) -> Conversation | None:
        result = await self._db.execute(select(Conversation).where(Conversation.id == conversation_id))
        return result.scalar_one_or_none()

    async def create(self, *, presentation_id: uuid.UUID | None, user_id: uuid.UUID | None = None, title: str | None = None) -> Conversation:
        conversation = Conversation(presentation_id=presentation_id, user_id=user_id, title=title)
        self._db.add(conversation)
        await self._db.flush()
        return conversation
