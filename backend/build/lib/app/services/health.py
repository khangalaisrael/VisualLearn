"""Health check service backing GET /health (docs/API_CONTRACT.md §7)."""

from dataclasses import dataclass

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings


@dataclass(frozen=True)
class HealthStatus:
    db: bool
    cache: bool
    model_provider: bool

    @property
    def status(self) -> str:
        return "ok" if (self.db and self.cache and self.model_provider) else "degraded"


class HealthService:
    """Checks connectivity of the stack's dependencies."""

    async def check(self, db: AsyncSession, redis: Redis) -> HealthStatus:
        return HealthStatus(
            db=await self._check_db(db),
            cache=await self._check_cache(redis),
            model_provider=self._check_model_provider(),
        )

    @staticmethod
    async def _check_db(db: AsyncSession) -> bool:
        try:
            await db.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    @staticmethod
    async def _check_cache(redis: Redis) -> bool:
        try:
            return bool(await redis.ping())
        except Exception:
            return False

    @staticmethod
    def _check_model_provider() -> bool:
        # Confirms a key is configured for whichever provider
        # app/api/deps.py would actually select (OpenAI first, then
        # Anthropic — see docs/adr/ADR-009-openai-as-active-vlm-provider.md),
        # not that the key is valid or that the provider's API is reachable.
        settings = get_settings()
        return bool(settings.openai_api_key or settings.anthropic_api_key)
