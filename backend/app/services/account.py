"""Account deletion: removes a user and everything that belongs to them.

Shared analysis-cache rows are keyed by image hash, not by account, so they
cannot be attributed to a user; they expire on their own under the normal
retention window (services/retention.py).
"""

import uuid

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orm import (
    CacheEntry,
    Conversation,
    Message,
    ObjectRecord,
    Presentation,
    ProWaitlistClick,
    RateLimitEvent,
    Session,
    Slide,
    UsageEvent,
    User,
)


async def delete_account(db: AsyncSession, user_id: uuid.UUID) -> None:
    conversation_ids = select(Conversation.id).where(Conversation.user_id == user_id)
    await db.execute(delete(Message).where(Message.conversation_id.in_(conversation_ids)))
    await db.execute(delete(Conversation).where(Conversation.user_id == user_id))

    presentation_ids = list((await db.execute(select(Presentation.id).where(Presentation.user_id == user_id))).scalars())
    slide_ids = select(Slide.id).where(Slide.presentation_id.in_(presentation_ids))
    await db.execute(delete(ObjectRecord).where(ObjectRecord.slide_id.in_(slide_ids)))
    await db.execute(delete(CacheEntry).where(CacheEntry.slide_id.in_(slide_ids)))
    await db.execute(delete(Slide).where(Slide.presentation_id.in_(presentation_ids)))
    await db.execute(delete(Presentation).where(Presentation.id.in_(presentation_ids)))

    await db.execute(delete(RateLimitEvent).where(RateLimitEvent.key == f"user:{user_id}"))
    await db.execute(delete(Session).where(Session.user_id == user_id))
    # Spend history stays, anonymised; the waitlist click log is personal and goes.
    await db.execute(update(UsageEvent).where(UsageEvent.user_id == user_id).values(user_id=None))
    await db.execute(delete(ProWaitlistClick).where(ProWaitlistClick.user_id == user_id))
    await db.execute(delete(User).where(User.id == user_id))
    await db.commit()
