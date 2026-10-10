"""Phase 4 (docs/PublicHostingMVP.md) — per-user/per-IP rate limits on the
two expensive endpoints. See app/models/orm.py's RateLimitEvent and
app/repositories/rate_limit_events.py for why this is Postgres-backed.
"""

from dataclasses import dataclass
from datetime import timedelta

from fastapi import HTTPException, status

from app.repositories.rate_limit_events import RateLimitEventRepository


def _describe_wait(seconds: int) -> str:
    hours = max(1, round(seconds / 3600))
    if hours < 48:
        return f"{hours} hour" + ("" if hours == 1 else "s")
    return f"{round(hours / 24)} days"


class RateLimitExceeded(HTTPException):
    """429 with a `Retry-After` header and a message meant to be shown
    directly to the student, not just logged."""

    def __init__(self, retry_after_seconds: int, reached: str):
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"You've reached {reached}. Try again in about {_describe_wait(retry_after_seconds)}.",
            headers={"Retry-After": str(retry_after_seconds)},
        )


@dataclass(frozen=True)
class Limit:
    window: timedelta
    maximum: int
    # Completes "You've reached ...", e.g. "today's limit for slide captures".
    reached: str


async def enforce_rate_limits(
    repo: RateLimitEventRepository,
    *,
    key: str,
    action: str,
    limits: list[Limit],
) -> None:
    """Raises `RateLimitExceeded` if `key` is over any of `limits` for
    `action`; otherwise records this occurrence and returns. When several
    limits are exceeded at once, the one with the longest wait is reported
    (telling someone "try again in 3 hours" when the monthly allowance is
    what actually blocks them would be wrong). The record happens here, after
    every check passed, so a rejected request never counts against anyone."""
    worst: tuple[int, str] | None = None
    for limit in limits:
        if await repo.count_recent(key, action, limit.window) >= limit.maximum:
            wait = await repo.seconds_until_next_slot(key, action, limit.window)
            if worst is None or wait > worst[0]:
                worst = (wait, limit.reached)
    if worst is not None:
        raise RateLimitExceeded(*worst)
    await repo.record(key, action)
