"""Repository for the `messages` table (docs/DATA_MODEL.md §3)."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orm import Message


class MessageRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(
        self,
        *,
        conversation_id: uuid.UUID,
        role: str,
        content: str,
        query_mode: str,
        referenced_object_ids: list[str],
    ) -> Message:
        message = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            query_mode=query_mode,
            referenced_object_ids=referenced_object_ids,
        )
        self._db.add(message)
        await self._db.flush()
        return message

    async def list_by_conversation(self, conversation_id: uuid.UUID) -> list[Message]:
        result = await self._db.execute(
            select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at)
        )
        return list(result.scalars().all())
