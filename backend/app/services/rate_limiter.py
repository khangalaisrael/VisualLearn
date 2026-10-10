"""Phase 4 (docs/PublicHostingMVP.md) — per-user/per-IP rate limits on the
two expensive endpoints, plus the global daily capacity cap. See
app/models/orm.py's RateLimitEvent and
app/repositories/rate_limit_events.py for why this is Postgres-backed.

Windows are calendar-based in one fixed timezone (`rate_limit_timezone`):
the daily window starts at local midnight and the monthly one on the 1st, so
"resets at midnight" and "resets on the 1st" are literally true.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status

from app.core import clock
from app.core.config import Settings
from app.repositories.rate_limit_events import RateLimitEventRepository

GLOBAL_CAPACITY_MESSAGE = (
    "We've hit today's capacity. We're a small student project and keep costs low. Back tomorrow!"
)


def _local_midnight(day: date, zone: ZoneInfo) -> datetime:
    return datetime.combine(day, time.min, tzinfo=zone).astimezone(timezone.utc)


def day_window(at: datetime, zone_name: str) -> tuple[datetime, datetime]:
    """(start, next start) of the local day containing `at`, in UTC."""
    zone = ZoneInfo(zone_name)
    today = at.astimezone(zone).date()
    return _local_midnight(today, zone), _local_midnight(today + timedelta(days=1), zone)


def month_window(at: datetime, zone_name: str) -> tuple[datetime, datetime]:
    """(start, next start) of the local calendar month containing `at`, in UTC."""
    zone = ZoneInfo(zone_name)
    first = at.astimezone(zone).date().replace(day=1)
    next_first = date(first.year + (first.month == 12), first.month % 12 + 1, 1)
    return _local_midnight(first, zone), _local_midnight(next_first, zone)


def _describe_wait(seconds: int) -> str:
    hours = max(1, round(seconds / 3600))
    if hours < 48:
        return f"{hours} hour" + ("" if hours == 1 else "s")
    return f"{round(hours / 24)} days"


class RateLimitExceeded(HTTPException):
    """429 with a `Retry-After` header, an `X-Limit-Kind` header the
    extension uses to pick the right card ("daily" | "monthly" | "global"),
    and a message meant to be shown directly to the student."""

    def __init__(self, *, kind: str, retry_after_seconds: int, detail: str):
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail,
            headers={"Retry-After": str(retry_after_seconds), "X-Limit-Kind": kind},
        )
        self.kind = kind


@dataclass(frozen=True)
class Limit:
    kind: str  # "daily" | "monthly"
    since: datetime
    resets_at: datetime
    maximum: int
    # Completes "You've reached ...", e.g. "today's limit for slide captures".
    reached: str


def capture_limits(settings: Settings, at: datetime, *, signed_in: bool = True) -> list[Limit]:
    """Signed-out requests (counted per IP address) get the smaller allowance."""
    day_start, day_end = day_window(at, settings.rate_limit_timezone)
    month_start, month_end = month_window(at, settings.rate_limit_timezone)
    per_day = settings.rate_limit_captures_per_day if signed_in else settings.rate_limit_anonymous_captures_per_day
    per_month = (
        settings.rate_limit_captures_per_month if signed_in else settings.rate_limit_anonymous_captures_per_month
    )
    return [
        Limit("daily", day_start, day_end, per_day, "today's limit for slide captures"),
        Limit(
            "monthly",
            month_start,
            month_end,
            per_month,
            f"this month's allowance of {per_month} slide captures",
        ),
    ]


def chat_limits(settings: Settings, at: datetime, *, signed_in: bool = True) -> list[Limit]:
    day_start, day_end = day_window(at, settings.rate_limit_timezone)
    per_day = (
        settings.rate_limit_chat_messages_per_day
        if signed_in
        else settings.rate_limit_anonymous_chat_messages_per_day
    )
    return [Limit("daily", day_start, day_end, per_day, "today's limit for chat messages")]


def seconds_until(moment: datetime, at: datetime) -> int:
    return max(0, int((moment - at).total_seconds()))


async def enforce_rate_limits(
    repo: RateLimitEventRepository,
    *,
    key: str,
    action: str,
    limits: list[Limit],
) -> None:
    """Raises `RateLimitExceeded` if `key` is over any of `limits` for
    `action`; otherwise records this occurrence and returns. When several
    limits are exceeded at once, the one that resets last is reported
    (telling someone "try again in 3 hours" when the monthly allowance is
    what actually blocks them would be wrong). The record happens after every
    check passed, so a rejected request never counts against anyone."""
    at = clock.now()
    worst: tuple[int, Limit] | None = None
    for limit in limits:
        if await repo.count_since(key, action, limit.since) >= limit.maximum:
            wait = seconds_until(limit.resets_at, at)
            if worst is None or wait > worst[0]:
                worst = (wait, limit)
    if worst is not None:
        wait, limit = worst
        raise RateLimitExceeded(
            kind=limit.kind,
            retry_after_seconds=wait,
            detail=f"You've reached {limit.reached}. Try again in about {_describe_wait(wait)}.",
        )
    await repo.record(key, action)


async def enforce_global_capture_cap(repo: RateLimitEventRepository, settings: Settings) -> None:
    at = clock.now()
    day_start, day_end = day_window(at, settings.rate_limit_timezone)
    if await repo.count_all_since("analyze", day_start) >= settings.global_captures_per_day:
        raise RateLimitExceeded(
            kind="global",
            retry_after_seconds=seconds_until(day_end, at),
            detail=GLOBAL_CAPACITY_MESSAGE,
        )


async def enforce_global_chat_cap(repo: RateLimitEventRepository, settings: Settings) -> None:
    at = clock.now()
    day_start, day_end = day_window(at, settings.rate_limit_timezone)
    if await repo.count_all_since("chat", day_start) >= settings.global_chat_messages_per_day:
        raise RateLimitExceeded(
            kind="global",
            retry_after_seconds=seconds_until(day_end, at),
            detail=GLOBAL_CAPACITY_MESSAGE,
        )
