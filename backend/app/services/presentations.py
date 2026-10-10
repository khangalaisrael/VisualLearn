"""Deleting a user's captures and lectures (and the chats attached to them)."""

import uuid
from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orm import CacheEntry, Conversation, Message, ObjectRecord, Presentation, Slide


async def delete_slides(db: AsyncSession, slide_ids: Sequence[uuid.UUID]) -> None:
    if not slide_ids:
        return
    conversation_ids = select(Conversation.id).where(Conversation.slide_id.in_(slide_ids))
    await db.execute(delete(Message).where(Message.conversation_id.in_(conversation_ids)))
    await db.execute(delete(Conversation).where(Conversation.slide_id.in_(slide_ids)))
    await db.execute(delete(ObjectRecord).where(ObjectRecord.slide_id.in_(slide_ids)))
    await db.execute(delete(CacheEntry).where(CacheEntry.slide_id.in_(slide_ids)))
    await db.execute(delete(Slide).where(Slide.id.in_(slide_ids)))


async def delete_presentation(db: AsyncSession, presentation_id: uuid.UUID) -> None:
    slide_ids = list((await db.execute(select(Slide.id).where(Slide.presentation_id == presentation_id))).scalars())
    await delete_slides(db, slide_ids)
    # Chats opened on the lecture but not tied to one slide.
    conversation_ids = select(Conversation.id).where(Conversation.presentation_id == presentation_id)
    await db.execute(delete(Message).where(Message.conversation_id.in_(conversation_ids)))
    await db.execute(delete(Conversation).where(Conversation.presentation_id == presentation_id))
    await db.execute(delete(Presentation).where(Presentation.id == presentation_id))
