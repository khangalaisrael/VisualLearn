"""Redis client factory.

Sprint 1 only uses Redis for the health check (docs/API_CONTRACT.md §7). The
analysis cache (docs/ARCHITECTURE.md §5) is a Milestone 2 feature — this
module is where that CacheService will source its connection from.
"""

from redis.asyncio import Redis

from app.core.config import get_settings

_settings = get_settings()

redis_client: Redis = Redis.from_url(_settings.redis_url, decode_responses=True)


async def get_redis() -> Redis:
    return redis_client
