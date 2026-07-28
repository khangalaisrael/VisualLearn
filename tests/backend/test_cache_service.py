"""Unit tests for CacheService (docs/ARCHITECTURE.md §5).

Uses the same `db_session` fixture as the API tests (tests/backend/conftest.py)
but calls the service directly rather than going through an HTTP request.
"""

from app.models.schemas import BoundingBox, SlideObject
from app.services.cache_service import CacheService
from app.services.slide_analyzer import AnalysisResult
from conftest import FakeRedis


def _result() -> AnalysisResult:
    return AnalysisResult(
        objects=[
            SlideObject(
                id="obj-1",
                type="title",
                bounding_box=BoundingBox(x=0, y=0, width=1, height=0.1),
                extracted_text="Hello",
                latex=None,
                summary=None,
                confidence=0.9,
            )
        ],
        summary="A test slide.",
    )


async def test_get_returns_none_when_not_cached(db_session) -> None:
    cache = CacheService(FakeRedis(), db_session)
    assert await cache.get("nonexistent-hash") is None


async def test_set_then_get_round_trips(db_session) -> None:
    cache = CacheService(FakeRedis(), db_session)
    result = _result()

    await cache.set("hash-1", result, model_used="claude-opus-4-8")
    await db_session.commit()

    retrieved = await cache.get("hash-1")
    assert retrieved is not None
    assert retrieved.summary == "A test slide."
    assert retrieved.objects[0].extracted_text == "Hello"
    assert retrieved.objects[0].type == "title"


async def test_get_backfills_redis_from_durable_store_after_redis_miss(db_session) -> None:
    # Simulate a Redis restart: write via one CacheService (populates both
    # Redis and cache_entries), then read via a second CacheService backed
    # by a *fresh* Redis instance (nothing cached, only cache_entries has it).
    writer = CacheService(FakeRedis(), db_session)
    await writer.set("hash-2", _result(), model_used="claude-opus-4-8")
    await db_session.commit()

    fresh_redis = FakeRedis()
    reader = CacheService(fresh_redis, db_session)

    retrieved = await reader.get("hash-2")
    assert retrieved is not None
    assert retrieved.summary == "A test slide."
    # Backfilled: the fresh Redis instance now holds the entry too.
    assert await fresh_redis.get("analysis:hash-2") is not None


async def test_different_hash_is_independent(db_session) -> None:
    cache = CacheService(FakeRedis(), db_session)
    await cache.set("hash-a", _result(), model_used="claude-opus-4-8")
    await db_session.commit()

    assert await cache.get("hash-b") is None


class _FailingRedis:
    """Simulates a Redis outage — every call raises."""

    async def ping(self):
        raise ConnectionError("redis unreachable")

    async def get(self, key: str):
        raise ConnectionError("redis unreachable")

    async def set(self, key: str, value: str, ex: int | None = None):
        raise ConnectionError("redis unreachable")


async def test_set_persists_to_durable_store_even_when_redis_is_down(db_session) -> None:
    cache = CacheService(_FailingRedis(), db_session)

    # Must not raise — a Redis outage degrades performance, it doesn't 500
    # the request (docs/ARCHITECTURE.md §6 "never crash").
    await cache.set("hash-down", _result(), model_used="claude-opus-4-8")
    await db_session.commit()


async def test_get_falls_back_to_durable_store_when_redis_is_down(db_session) -> None:
    # Populate cache_entries via a working Redis first...
    writer = CacheService(FakeRedis(), db_session)
    await writer.set("hash-resilient", _result(), model_used="claude-opus-4-8")
    await db_session.commit()

    # ...then read it back with Redis unavailable. Must not raise, and must
    # still return the cached result from Postgres.
    reader = CacheService(_FailingRedis(), db_session)
    retrieved = await reader.get("hash-resilient")

    assert retrieved is not None
    assert retrieved.summary == "A test slide."
