"""Repository for the `cache_entries` table (docs/DATA_MODEL.md §3) — the
durable backing store for the Redis analysis cache."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orm import CacheEntry


class CacheEntryRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_hash(self, image_hash: str) -> CacheEntry | None:
        result = await self._db.execute(select(CacheEntry).where(CacheEntry.image_hash == image_hash))
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        image_hash: str,
        analysis_result: dict,
        model_used: str,
        expires_at: datetime,
    ) -> CacheEntry:
        entry = CacheEntry(
            image_hash=image_hash,
            analysis_result=analysis_result,
            model_used=model_used,
            expires_at=expires_at,
        )
        self._db.add(entry)
        await self._db.flush()
        return entry
