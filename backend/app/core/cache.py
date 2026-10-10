"""Redis client factory. Redis is optional: with no REDIS_URL configured
`get_redis` yields None and the analysis cache runs on Postgres alone
(services/cache_service.py)."""

from redis.asyncio import Redis

from app.core.config import get_settings

_settings = get_settings()

redis_client: Redis | None = Redis.from_url(_settings.redis_url, decode_responses=True) if _settings.redis_url else None


async def get_redis() -> Redis | None:
    return redis_client
