"""CacheService — analysis cache keyed by slide image hash (docs/ARCHITECTURE.md §5).

Two layers: Redis is the hot path (fast lookups, ~1ms); `cache_entries`
(PostgreSQL) is the durable backing store, so a cache entry survives a
Redis restart — a lookup that misses Redis but hits `cache_entries`
backfills Redis before returning, so subsequent lookups are fast again.

Redis errors are caught and logged rather than raised: it's a hot-path
optimization, not a correctness dependency, and letting a Redis outage 500
the whole analyze request would violate docs/ARCHITECTURE.md §6's "never
crash" error-handling principle. `cache_entries` (Postgres) is the source
of truth `get()` falls back to; `set()` still persists there even if the
Redis write fails.

Keyed globally by image hash, not scoped to a presentation: the same
screenshot bytes reappearing in a different deck should still skip the
Claude call (see api/v1/slides.py for how this differs from the
presentation-scoped slide de-duplication in repositories/slides.py).
"""

import json
import logging
from datetime import UTC, datetime, timedelta

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import SlideObject
from app.repositories.cache_entries import CacheEntryRepository
from app.services.slide_analyzer import AnalysisResult

logger = logging.getLogger(__name__)

_REDIS_KEY_PREFIX = "analysis:"
_REDIS_TTL_SECONDS = 60 * 60 * 24 * 7  # 7 days. cache_entries has no TTL enforcement
# of its own (expires_at is advisory, per docs/DATA_MODEL.md) — correctness
# comes from image_hash uniqueness, not from either expiry.


class CacheService:
    def __init__(self, redis: Redis, db: AsyncSession) -> None:
        self._redis = redis
        self._cache_entries = CacheEntryRepository(db)

    async def get(self, image_hash: str) -> AnalysisResult | None:
        redis_key = _REDIS_KEY_PREFIX + image_hash
        cached_json = await self._safe_redis_get(redis_key)
        if cached_json is not None:
            return self._deserialize(cached_json)

        entry = await self._cache_entries.get_by_hash(image_hash)
        if entry is None:
            return None

        cached_json = json.dumps(entry.analysis_result)
        await self._safe_redis_set(redis_key, cached_json)
        return self._deserialize(cached_json)

    async def set(self, image_hash: str, result: AnalysisResult, *, model_used: str) -> None:
        serialized = self._serialize(result)
        cached_json = json.dumps(serialized)

        await self._safe_redis_set(_REDIS_KEY_PREFIX + image_hash, cached_json)
        await self._cache_entries.create(
            image_hash=image_hash,
            analysis_result=serialized,
            model_used=model_used,
            expires_at=datetime.now(UTC) + timedelta(seconds=_REDIS_TTL_SECONDS),
        )

    async def _safe_redis_get(self, key: str) -> str | None:
        try:
            return await self._redis.get(key)
        except Exception:
            logger.warning("cache_service_redis_get_failed key=%s", key, exc_info=True)
            return None

    async def _safe_redis_set(self, key: str, value: str) -> None:
        try:
            await self._redis.set(key, value, ex=_REDIS_TTL_SECONDS)
        except Exception:
            logger.warning("cache_service_redis_set_failed key=%s", key, exc_info=True)

    @staticmethod
    def _serialize(result: AnalysisResult) -> dict:
        return {
            "summary": result.summary,
            "objects": [obj.model_dump(mode="json") for obj in result.objects],
        }

    @staticmethod
    def _deserialize(cached_json: str) -> AnalysisResult:
        payload = json.loads(cached_json)
        objects = [SlideObject.model_validate(o) for o in payload["objects"]]
        return AnalysisResult(objects=objects, summary=payload["summary"])
