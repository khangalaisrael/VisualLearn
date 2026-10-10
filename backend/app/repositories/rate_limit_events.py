"""Repository for the `rate_limit_events` table (docs/PublicHostingMVP.md
Phase 4). See app/models/orm.py's RateLimitEvent docstring for why this is
Postgres-backed rather than Redis."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orm import RateLimitEvent

WINDOW = timedelta(hours=24)


class RateLimitEventRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def count_recent(self, key: str, action: str) -> int:
        since = datetime.now(timezone.utc) - WINDOW
        result = await self._db.execute(
            select(func.count())
            .select_from(RateLimitEvent)
            .where(RateLimitEvent.key == key, RateLimitEvent.action == action, RateLimitEvent.created_at >= since)
        )
        return result.scalar_one()

    async def record(self, key: str, action: str) -> None:
        self._db.add(RateLimitEvent(key=key, action=action))
        await self._db.flush()

    async def seconds_until_next_slot(self, key: str, action: str) -> int:
        """How long until the oldest event in the current 24h window ages
        out, freeing up a slot — what a "try again in X" message tells the
        caller. Used only once the limit has already been hit, so a result
        is always found (the count that triggered the 429 is itself
        at least one row in this window)."""
        since = datetime.now(timezone.utc) - WINDOW
        result = await self._db.execute(
            select(func.min(RateLimitEvent.created_at)).where(
                RateLimitEvent.key == key, RateLimitEvent.action == action, RateLimitEvent.created_at >= since
            )
        )
        oldest = result.scalar_one()
        if oldest is None:
            return 0
        if oldest.tzinfo is None:
            # Same SQLite-vs-Postgres timezone round-trip gotcha as
            # sessions.py's get_valid_by_token — see that docstring.
            oldest = oldest.replace(tzinfo=timezone.utc)
        resets_at = oldest + WINDOW
        return max(0, int((resets_at - datetime.now(timezone.utc)).total_seconds()))
