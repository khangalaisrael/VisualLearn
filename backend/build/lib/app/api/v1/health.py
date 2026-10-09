"""GET /health — docs/API_CONTRACT.md §7."""

from fastapi import APIRouter, Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import get_redis
from app.db.session import get_db
from app.models.schemas import HealthResponse
from app.services.health import HealthService

router = APIRouter(tags=["health"])
_health_service = HealthService()


@router.get("/health", response_model=HealthResponse)
async def get_health(
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> HealthResponse:
    result = await _health_service.check(db, redis)
    return HealthResponse(
        status=result.status,
        db=result.db,
        cache=result.cache,
        model_provider=result.model_provider,
    )
