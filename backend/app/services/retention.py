"""Data retention: chats and the slide content behind them are deleted
`chat_retention_days` after their last use. Run daily by an external
scheduler hitting POST /maintenance/cleanup (the hosting plan has no
scheduled jobs of its own). Read paths also filter by the same cutoff, so
an expired chat never shows even if a run is missed.
"""

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.orm import (
    CacheEntry,
    Conversation,
    Message,
    ObjectRecord,
    Presentation,
    RateLimitEvent,
    Session,
    Slide,
)

# The monthly capture allowance counts events over a rolling 30 days; the
# extra day is slack.
_RATE_LIMIT_EVENT_LIFETIME = timedelta(days=31)


def retention_cutoff() -> datetime:
    return datetime.now(UTC) - timedelta(days=get_settings().chat_retention_days)


@dataclass(frozen=True)
class CleanupResult:
    conversations: int
    presentations: int
    cache_entries: int
    rate_limit_events: int
    sessions: int

    def as_dict(self) -> dict[str, int]:
        return asdict(self)


async def run_cleanup(db: AsyncSession) -> CleanupResult:
    now = datetime.now(UTC)
    cutoff = retention_cutoff()

    expired_conversations = select(Conversation.id).where(Conversation.last_activity_at < cutoff)
    await db.execute(delete(Message).where(Message.conversation_id.in_(expired_conversations)))
    conversations = await db.execute(delete(Conversation).where(Conversation.last_activity_at < cutoff))

    # A capture goes once it is past the cutoff and no surviving chat still
    # refers to it. Ids are materialized so the deletes below cannot change
    # which rows match.
    old_slide_ids = list(
        (
            await db.execute(
                select(Slide.id).where(
                    Slide.created_at < cutoff,
                    ~exists().where(Conversation.slide_id == Slide.id),
                )
            )
        )
        .scalars()
        .all()
    )
    await db.execute(delete(ObjectRecord).where(ObjectRecord.slide_id.in_(old_slide_ids)))
    await db.execute(delete(CacheEntry).where(CacheEntry.slide_id.in_(old_slide_ids)))
    await db.execute(delete(Slide).where(Slide.id.in_(old_slide_ids)))
    # A lecture goes once it is past the cutoff with no captures or chats left.
    presentations = await db.execute(
        delete(Presentation).where(
            Presentation.created_at < cutoff,
            ~exists().where(Slide.presentation_id == Presentation.id),
            ~exists().where(Conversation.presentation_id == Presentation.id),
        )
    )

    cache_entries = await db.execute(delete(CacheEntry).where(CacheEntry.created_at < cutoff))
    rate_limit_events = await db.execute(
        delete(RateLimitEvent).where(RateLimitEvent.created_at < now - _RATE_LIMIT_EVENT_LIFETIME)
    )
    sessions = await db.execute(delete(Session).where(Session.expires_at < now))
    await db.commit()

    return CleanupResult(
        conversations=conversations.rowcount,
        presentations=presentations.rowcount,
        cache_entries=cache_entries.rowcount,
        rate_limit_events=rate_limit_events.rowcount,
        sessions=sessions.rowcount,
    )
