"""Repository for the `rate_limit_events` table (docs/PublicHostingMVP.md
Phase 4). See app/models/orm.py's RateLimitEvent docstring for why this is
Postgres-backed rather than Redis. Windows are calendar-based (since local
midnight / since the 1st), computed by services/rate_limiter.py; this layer
only counts rows since an instant."""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.models.orm import RateLimitEvent


class RateLimitEventRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def count_since(self, key: str, action: str, since: datetime) -> int:
        result = await self._db.execute(
            select(func.count())
            .select_from(RateLimitEvent)
            .where(RateLimitEvent.key == key, RateLimitEvent.action == action, RateLimitEvent.created_at >= since)
        )
        return result.scalar_one()

    async def count_all_since(self, action: str, since: datetime) -> int:
        """Every key combined — the global daily cap."""
        result = await self._db.execute(
            select(func.count())
            .select_from(RateLimitEvent)
            .where(RateLimitEvent.action == action, RateLimitEvent.created_at >= since)
        )
        return result.scalar_one()

    async def record(self, key: str, action: str) -> None:
        # created_at comes from the app clock, not the database default, so
        # it agrees with the window boundaries (and with a test's fake clock).
        self._db.add(RateLimitEvent(key=key, action=action, created_at=clock.now()))
        await self._db.flush()
