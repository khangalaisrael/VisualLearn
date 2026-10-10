"""Phase 4 (docs/PublicHostingMVP.md) — per-user/per-IP daily rate limits
on the two expensive endpoints. See app/models/orm.py's RateLimitEvent and
app/repositories/rate_limit_events.py for why this is Postgres-backed.
"""

from fastapi import HTTPException, status

from app.repositories.rate_limit_events import RateLimitEventRepository


class RateLimitExceeded(HTTPException):
    """429 with a `Retry-After` header and a message meant to be shown
    directly to the student (docs/PublicHostingMVP.md Phase 4: "a clear
    'rate limited, try again in X' response the extension surfaces instead
    of a raw error"), not just logged."""

    def __init__(self, retry_after_seconds: int, action_description: str):
        hours = max(1, round(retry_after_seconds / 3600))
        unit = "hour" if hours == 1 else "hours"
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"You've reached today's limit for {action_description}. Try again in about {hours} {unit}.",
            headers={"Retry-After": str(retry_after_seconds)},
        )


async def enforce_rate_limit(
    repo: RateLimitEventRepository,
    *,
    key: str,
    action: str,
    limit: int,
    action_description: str,
) -> None:
    """Raises `RateLimitExceeded` if `key` has already performed `action`
    `limit` times in the last 24h; otherwise records this occurrence and
    returns. The record happens here, inside the same check — a caller
    that calls this once per request never needs to remember to record
    separately, and a request that gets rejected is never itself counted
    (checked before the insert, not after)."""
    count = await repo.count_recent(key, action)
    if count >= limit:
        retry_after = await repo.seconds_until_next_slot(key, action)
        raise RateLimitExceeded(retry_after, action_description)
    await repo.record(key, action)
