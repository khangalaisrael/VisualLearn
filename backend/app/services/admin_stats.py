"""Numbers for the admin dashboard: spend, per-user usage, outliers, waitlist.

Everything is derived from `usage_events` (never purged, estimated cost),
`rate_limit_events` (what the global cap counts) and `pro_waitlist_clicks`.
Per-day figures use the same local calendar days as the limits, so "today"
here is the same "today" a student's counter shows. Volumes are tiny (a
handful of users), so rows are fetched once and grouped in Python.
"""

import statistics
import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.orm import ProWaitlistClick, UsageEvent, User
from app.models.schemas import (
    AdminDay,
    AdminOverview,
    AdminUser,
    AdminUsersResponse,
    AdminWaitlistEntry,
    AdminWaitlistResponse,
)
from app.repositories.rate_limit_events import RateLimitEventRepository
from app.services.rate_limiter import day_window, month_window

SERIES_DAYS = 14
WINDOW_DAYS = 30
# Below this, an "outlier" is just noise: a few cents of spend isn't a problem.
OUTLIER_MIN_COST_USD = 0.01
OUTLIER_MEDIAN_MULTIPLE = 2.0


def _utc(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def outlier_ids(costs: dict[object, float]) -> set[object]:
    """Who spent far more than the typical user: more than twice the median
    of everyone who spent anything, and at least a cent. Needs three people
    with spend, otherwise there is no "typical" to compare with."""
    spending = [cost for cost in costs.values() if cost > 0]
    if len(spending) < 3:
        return set()
    threshold = max(OUTLIER_MEDIAN_MULTIPLE * statistics.median(spending), OUTLIER_MIN_COST_USD)
    return {key for key, cost in costs.items() if cost > threshold}


async def _events_since(db: AsyncSession, since: datetime) -> list[UsageEvent]:
    result = await db.execute(select(UsageEvent).where(UsageEvent.created_at >= since))
    return list(result.scalars().all())


async def build_overview(db: AsyncSession, settings: Settings, now: datetime) -> AdminOverview:
    zone = ZoneInfo(settings.rate_limit_timezone)
    day_start, _ = day_window(now, settings.rate_limit_timezone)
    month_start, _ = month_window(now, settings.rate_limit_timezone)
    events = await _events_since(db, min(now - timedelta(days=WINDOW_DAYS), month_start))

    today = now.astimezone(zone).date()
    days = {today - timedelta(days=offset): AdminDay(date=(today - timedelta(days=offset)).isoformat())
            for offset in range(SERIES_DAYS)}
    cost_30d = cost_month = 0.0
    active_today: set[uuid.UUID] = set()
    for event in events:
        created = _utc(event.created_at)
        cost = event.est_cost_usd or 0.0
        if created >= now - timedelta(days=WINDOW_DAYS):
            cost_30d += cost
        if created >= month_start:
            cost_month += cost
        day = days.get(created.astimezone(zone).date())
        if day is not None:
            if event.action == "analyze":
                day.captures += 1
                day.cost_usd += cost
            elif event.action == "chat":
                day.chats += 1
                day.cost_usd += cost
            elif event.action.startswith("limit_hit"):
                day.limit_hits += 1
        if created >= day_start and event.user_id is not None and event.action in ("analyze", "chat"):
            active_today.add(event.user_id)

    series = [days[day] for day in sorted(days)]
    for day in series:
        day.cost_usd = round(day.cost_usd, 4)

    clicks = (await db.execute(select(func.count(), func.count(func.distinct(ProWaitlistClick.user_id))))).one()
    total_users = (await db.execute(select(func.count()).select_from(User))).scalar_one()
    return AdminOverview(
        generated_at=now,
        timezone=settings.rate_limit_timezone,
        global_captures_today=await RateLimitEventRepository(db).count_all_since("analyze", day_start),
        global_cap=settings.global_captures_per_day,
        cost_today_usd=series[-1].cost_usd,
        cost_month_usd=round(cost_month, 4),
        cost_30d_usd=round(cost_30d, 4),
        active_users_today=len(active_today),
        total_users=total_users,
        limit_hits_today=series[-1].limit_hits,
        waitlist_clicks=clicks[0],
        waitlist_users=clicks[1],
        days=series,
    )


async def build_users(db: AsyncSession, now: datetime) -> AdminUsersResponse:
    since = now - timedelta(days=WINDOW_DAYS)
    events = await _events_since(db, since)
    users = {user.id: user for user in (await db.execute(select(User))).scalars().all()}

    rows: dict[uuid.UUID | None, AdminUser] = {
        user_id: AdminUser(user_id=str(user_id), email=user.email) for user_id, user in users.items()
    }
    for event in events:
        row = rows.get(event.user_id)
        if row is None:  # signed out, or an account that was deleted (history is anonymised)
            row = rows[event.user_id] = AdminUser(user_id=None, email=None)
        created = _utc(event.created_at)
        if event.action == "analyze":
            row.captures_30d += 1
        elif event.action == "chat":
            row.chats_30d += 1
        elif event.action.startswith("limit_hit"):
            row.limit_hits_30d += 1
        if event.action in ("analyze", "chat"):
            row.input_tokens += event.input_tokens or 0
            row.output_tokens += event.output_tokens or 0
            row.cost_30d_usd += event.est_cost_usd or 0.0
            if row.last_active is None or created > row.last_active:
                row.last_active = created

    flagged = outlier_ids({key: row.cost_30d_usd for key, row in rows.items()})
    for key, row in rows.items():
        row.cost_30d_usd = round(row.cost_30d_usd, 4)
        row.is_outlier = key in flagged

    ordered = sorted(rows.values(), key=lambda row: (row.cost_30d_usd, row.captures_30d), reverse=True)
    spending = [row.cost_30d_usd for row in ordered if row.cost_30d_usd > 0]
    return AdminUsersResponse(
        median_cost_usd=round(statistics.median(spending), 4) if spending else 0.0,
        users=ordered,
    )


async def build_waitlist(db: AsyncSession) -> AdminWaitlistResponse:
    rows = (
        await db.execute(
            select(ProWaitlistClick, User.email)
            .join(User, User.id == ProWaitlistClick.user_id)
            .order_by(ProWaitlistClick.created_at)
        )
    ).all()
    grouped: dict[uuid.UUID, AdminWaitlistEntry] = {}
    sources: dict[uuid.UUID, set[str]] = defaultdict(set)
    for click, email in rows:
        created = _utc(click.created_at)
        entry = grouped.get(click.user_id)
        if entry is None:
            entry = grouped[click.user_id] = AdminWaitlistEntry(
                email=email, clicks=0, first_click=created, last_click=created, sources=[]
            )
        entry.clicks += 1
        entry.last_click = created
        sources[click.user_id].add(click.source)
    for user_id, entry in grouped.items():
        entry.sources = sorted(sources[user_id])
    entries = sorted(grouped.values(), key=lambda entry: entry.last_click, reverse=True)
    return AdminWaitlistResponse(unique_users=len(entries), total_clicks=len(rows), entries=entries)
