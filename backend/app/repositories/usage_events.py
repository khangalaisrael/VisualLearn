"""Repository for `usage_events` (spend/limit-hit records) and
`pro_waitlist_clicks`."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.models.orm import ProWaitlistClick, UsageEvent


class UsageEventRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def record(
        self,
        *,
        user_id: uuid.UUID | None,
        action: str,
        model: str | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_hit: bool = False,
        est_cost_usd: float = 0.0,
        slide_id: uuid.UUID | None = None,
        conversation_id: uuid.UUID | None = None,
    ) -> UsageEvent:
        event = UsageEvent(
            user_id=user_id,
            action=action,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_hit=cache_hit,
            est_cost_usd=est_cost_usd,
            slide_id=slide_id,
            conversation_id=conversation_id,
            created_at=clock.now(),
        )
        self._db.add(event)
        await self._db.flush()
        return event


class ProWaitlistRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def record_click(self, user_id: uuid.UUID, source: str) -> None:
        self._db.add(ProWaitlistClick(user_id=user_id, source=source, created_at=clock.now()))
        await self._db.flush()
