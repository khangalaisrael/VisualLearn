"""Phase 4 — per-user/per-IP daily and monthly limits, the global capacity
cap, and the admin bypass (docs/PublicHostingMVP.md).

The clock is fixed so day/month boundaries are exact and the tests don't
depend on the date they run. "Now" is 12:00 in Africa/Johannesburg
(UTC+2, no DST), so local midnight is 22:00 UTC and the next 1st is
22:00 UTC on the last day of the month.
"""

import io
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.core.config import get_settings
from app.models.orm import RateLimitEvent, UsageEvent, User
from app.models.orm import Session as SessionRow
from app.services.google_oauth import parse_userinfo
from app.services.rate_limiter import GLOBAL_CAPACITY_MESSAGE

T0 = datetime(2026, 10, 10, 10, 0, tzinfo=UTC)  # 12:00 Johannesburg
API_KEY = {"X-API-Key": "test-api-key"}


class FakeClock:
    def __init__(self) -> None:
        self.value = T0


@pytest.fixture(autouse=True)
def fake_clock(monkeypatch) -> FakeClock:
    fake = FakeClock()
    monkeypatch.setattr(clock, "now", lambda: fake.value)
    return fake


@pytest.fixture(autouse=True)
def low_limits():
    """Small caps so a test can reach them without dozens of requests.
    get_settings() is @lru_cache'd and shared with the running app, so the
    attributes are mutated in place and restored afterwards."""
    settings = get_settings()
    names = (
        "rate_limit_captures_per_day",
        "rate_limit_captures_per_month",
        "rate_limit_chat_messages_per_day",
        "rate_limit_anonymous_captures_per_day",
        "rate_limit_anonymous_captures_per_month",
        "rate_limit_anonymous_chat_messages_per_day",
        "global_captures_per_day",
        "global_chat_messages_per_day",
        "admin_emails",
    )
    original = {name: getattr(settings, name) for name in names}
    settings.rate_limit_captures_per_day = 2
    settings.rate_limit_captures_per_month = 400
    settings.rate_limit_chat_messages_per_day = 2
    # The signed-out allowance equals the signed-in one here, so the tests below
    # exercise one limit at a time; the dedicated tests at the bottom set it apart.
    settings.rate_limit_anonymous_captures_per_day = 2
    settings.rate_limit_anonymous_captures_per_month = 400
    settings.rate_limit_anonymous_chat_messages_per_day = 2
    settings.global_captures_per_day = 1000
    settings.global_chat_messages_per_day = 1000
    settings.admin_emails = ""
    yield settings
    for name, value in original.items():
        setattr(settings, name, value)


def _png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (10, 10), color="white").save(buffer, format="PNG")
    return buffer.getvalue()


async def _capture(client: AsyncClient, headers: dict[str, str] | None = None):
    return await client.post(
        "/api/v1/slides/analyze",
        files={"image": ("slide.png", _png(), "image/png")},
        data={"slide_number": "1"},
        headers=headers or API_KEY,
    )


async def _sign_in(db_session: AsyncSession, email: str) -> tuple[dict[str, str], uuid.UUID]:
    user = User(id=uuid.uuid4(), google_sub=f"sub-{email}", email=email)
    db_session.add(user)
    await db_session.flush()
    token = f"token-{email}"
    db_session.add(SessionRow(id=uuid.uuid4(), user_id=user.id, token=token, expires_at=T0 + timedelta(days=1)))
    await db_session.commit()
    return {**API_KEY, "Authorization": f"Bearer {token}"}, user.id


async def _anonymous_key(db_session: AsyncSession) -> str:
    """The test transport's rate-limit key, read back after a first capture
    rather than hardcoding how it reports its address."""
    return (await db_session.execute(select(RateLimitEvent.key))).scalars().first()


async def _seed_events(db_session: AsyncSession, key: str, action: str, *when: datetime) -> None:
    for created_at in when:
        db_session.add(RateLimitEvent(key=key, action=action, created_at=created_at))
    await db_session.commit()


# --- daily window -----------------------------------------------------------


async def test_allows_requests_up_to_the_limit(client: AsyncClient) -> None:
    assert (await _capture(client)).status_code == 200
    assert (await _capture(client)).status_code == 200


async def test_blocks_the_request_past_the_limit_with_a_student_facing_429(client: AsyncClient) -> None:
    await _capture(client)
    await _capture(client)
    blocked = await _capture(client)

    assert blocked.status_code == 429
    assert blocked.headers["X-Limit-Kind"] == "daily"
    assert int(blocked.headers["Retry-After"]) == 12 * 3600  # 12:00 -> local midnight
    detail = blocked.json()["detail"]
    assert "today's limit for slide captures" in detail
    assert "12 hours" in detail


async def test_a_rejected_request_does_not_itself_count(client: AsyncClient, db_session: AsyncSession) -> None:
    await _capture(client)
    await _capture(client)
    assert (await _capture(client)).status_code == 429
    assert (await _capture(client)).status_code == 429
    assert (await db_session.execute(select(func.count()).select_from(RateLimitEvent))).scalar_one() == 2


async def test_daily_limit_resets_at_local_midnight_not_after_24_hours(
    client: AsyncClient, fake_clock: FakeClock
) -> None:
    await _capture(client)
    await _capture(client)

    fake_clock.value = datetime(2026, 10, 10, 21, 59, tzinfo=UTC)  # 23:59 local
    assert (await _capture(client)).status_code == 429
    fake_clock.value = datetime(2026, 10, 10, 22, 0, tzinfo=UTC)  # 00:00 local, new day
    assert (await _capture(client)).status_code == 200


async def test_chat_and_capture_limits_are_independent(client: AsyncClient) -> None:
    captured = (await _capture(client)).json()
    await _capture(client)
    assert (await _capture(client)).status_code == 429

    payload = {
        "conversation_id": None,
        "presentation_id": captured["presentation_id"],
        "query_mode": "slide",
        "slide_id": captured["slide_id"],
        "object_id": None,
        "message": "Explain this slide.",
    }
    assert (await client.post("/api/v1/chat", json=payload, headers=API_KEY)).status_code == 200


# --- monthly window ---------------------------------------------------------


async def test_monthly_allowance_blocks_even_when_the_day_has_room(
    client: AsyncClient, db_session: AsyncSession, low_limits
) -> None:
    low_limits.rate_limit_captures_per_day = 10
    low_limits.rate_limit_captures_per_month = 3
    low_limits.rate_limit_anonymous_captures_per_month = 3  # these tests run signed out
    assert (await _capture(client)).status_code == 200
    key = await _anonymous_key(db_session)
    await _seed_events(
        db_session, key, "analyze", datetime(2026, 10, 2, 12, 0, tzinfo=UTC), datetime(2026, 10, 3, 12, 0, tzinfo=UTC)
    )

    blocked = await _capture(client)
    assert blocked.status_code == 429
    assert blocked.headers["X-Limit-Kind"] == "monthly"
    assert "this month's allowance of 3" in blocked.json()["detail"]
    # Resets on the 1st, 00:00 local = Oct 31 22:00 UTC: 21 days 12 hours away.
    assert int(blocked.headers["Retry-After"]) == (21 * 24 + 12) * 3600
    assert "days" in blocked.json()["detail"]


async def test_month_boundary_is_local_midnight_on_the_first(
    client: AsyncClient, db_session: AsyncSession, low_limits
) -> None:
    low_limits.rate_limit_captures_per_day = 10
    low_limits.rate_limit_captures_per_month = 2
    low_limits.rate_limit_anonymous_captures_per_month = 2  # these tests run signed out
    assert (await _capture(client)).status_code == 200  # creates this client's key
    key = await _anonymous_key(db_session)
    await db_session.execute(RateLimitEvent.__table__.delete())
    await db_session.commit()
    await _seed_events(
        db_session,
        key,
        "analyze",
        datetime(2026, 9, 30, 21, 0, tzinfo=UTC),  # 23:00 on Sep 30 local: last month, ignored
        datetime(2026, 9, 30, 22, 30, tzinfo=UTC),  # 00:30 on Oct 1 local: counts
    )

    assert (await _capture(client)).status_code == 200  # 1 (Oct 1) + this = 2
    assert (await _capture(client)).status_code == 429  # would be a third


# --- global capacity cap ----------------------------------------------------


async def test_global_cap_blocks_everyone_with_the_capacity_message(
    client: AsyncClient, db_session: AsyncSession, low_limits
) -> None:
    low_limits.global_captures_per_day = 3
    await _seed_events(db_session, "ip:10.0.0.1", "analyze", T0, T0, T0)

    blocked = await _capture(client)
    assert blocked.status_code == 429
    assert blocked.headers["X-Limit-Kind"] == "global"
    assert blocked.json()["detail"] == GLOBAL_CAPACITY_MESSAGE
    assert int(blocked.headers["Retry-After"]) == 12 * 3600


async def test_yesterdays_captures_do_not_count_towards_the_global_cap(
    client: AsyncClient, db_session: AsyncSession, low_limits
) -> None:
    low_limits.global_captures_per_day = 2
    yesterday = datetime(2026, 10, 9, 21, 0, tzinfo=UTC)  # 23:00 local, day before
    await _seed_events(db_session, "ip:10.0.0.1", "analyze", yesterday, yesterday, yesterday)
    assert (await _capture(client)).status_code == 200


# --- limit hits are recorded as a demand signal -----------------------------


async def test_limit_hits_are_recorded_even_though_the_request_is_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _capture(client)
    await _capture(client)
    await _capture(client)
    actions = (
        await db_session.execute(select(UsageEvent.action).where(UsageEvent.action.like("limit_hit%")))
    ).scalars().all()
    assert actions == ["limit_hit_daily"]


# --- admin ------------------------------------------------------------------


async def test_admin_has_no_limits_and_is_not_counted(
    client: AsyncClient, db_session: AsyncSession, low_limits
) -> None:
    low_limits.admin_emails = " Boss@Example.com , other@example.com"
    low_limits.global_captures_per_day = 1
    await _seed_events(db_session, "ip:10.0.0.1", "analyze", T0, T0)  # global cap already exceeded
    headers, user_id = await _sign_in(db_session, "boss@example.com")

    for _ in range(5):
        assert (await _capture(client, headers)).status_code == 200

    counted = await db_session.execute(
        select(func.count()).select_from(RateLimitEvent).where(RateLimitEvent.key == f"user:{user_id}")
    )
    assert counted.scalar_one() == 0


async def test_a_signed_in_non_admin_is_still_limited_on_their_own_key(
    client: AsyncClient, db_session: AsyncSession, low_limits
) -> None:
    low_limits.admin_emails = "boss@example.com"
    headers, _ = await _sign_in(db_session, "student@example.com")
    await _capture(client, headers)
    await _capture(client, headers)
    assert (await _capture(client, headers)).status_code == 429


def test_unverified_google_email_is_dropped_so_it_can_never_match_the_admin_list() -> None:
    assert parse_userinfo({"email": "a@b.com", "email_verified": False}, "sub").email is None
    assert parse_userinfo({"email": "a@b.com", "email_verified": True}, "sub").email == "a@b.com"
    assert parse_userinfo({"email": "a@b.com"}, "sub").email == "a@b.com"


# --- signed-out allowance and the global chat cap -------------------------------------------


def _chat_payload(captured: dict) -> dict:
    return {
        "conversation_id": None,
        "presentation_id": captured["presentation_id"],
        "query_mode": "slide",
        "slide_id": captured["slide_id"],
        "object_id": None,
        "message": "Explain this slide.",
    }


async def test_signed_out_captures_get_a_smaller_daily_allowance(
    client: AsyncClient, db_session: AsyncSession, low_limits
) -> None:
    low_limits.rate_limit_captures_per_day = 3
    low_limits.rate_limit_anonymous_captures_per_day = 1
    assert (await _capture(client)).status_code == 200
    blocked = await _capture(client)
    assert blocked.status_code == 429
    assert blocked.headers["X-Limit-Kind"] == "daily"

    # a signed-in account on the same connection still has its full allowance
    headers, _ = await _sign_in(db_session, "student@example.com")
    for _ in range(3):
        assert (await _capture(client, headers)).status_code == 200
    assert (await _capture(client, headers)).status_code == 429


async def test_signed_out_monthly_allowance_is_smaller_too(
    client: AsyncClient, db_session: AsyncSession, low_limits
) -> None:
    low_limits.rate_limit_captures_per_month = 400
    low_limits.rate_limit_anonymous_captures_per_month = 3
    low_limits.rate_limit_anonymous_captures_per_day = 50
    await _capture(client)
    key = await _anonymous_key(db_session)
    earlier_this_month = T0 - timedelta(days=3)
    await _seed_events(db_session, key, "analyze", earlier_this_month, earlier_this_month)

    blocked = await _capture(client)
    assert blocked.status_code == 429
    assert limit_kind(blocked) == "monthly"
    assert "3 slide captures" in blocked.json()["detail"]


def limit_kind(response) -> str:
    return response.headers["X-Limit-Kind"]


async def test_usage_reports_the_signed_out_allowance_to_signed_out_visitors(
    client: AsyncClient, db_session: AsyncSession, low_limits
) -> None:
    low_limits.rate_limit_captures_per_day = 20
    low_limits.rate_limit_anonymous_captures_per_day = 5
    low_limits.rate_limit_anonymous_captures_per_month = 100
    low_limits.rate_limit_captures_per_month = 400

    signed_out = (await client.get("/api/v1/usage", headers=API_KEY)).json()
    assert signed_out["captures_today"]["limit"] == 5
    assert signed_out["captures_month"]["limit"] == 100

    headers, _ = await _sign_in(db_session, "student@example.com")
    signed_in = (await client.get("/api/v1/usage", headers=headers)).json()
    assert signed_in["captures_today"]["limit"] == 20
    assert signed_in["captures_month"]["limit"] == 400


async def test_signed_out_chat_gets_a_smaller_allowance(client: AsyncClient, db_session: AsyncSession, low_limits) -> None:
    low_limits.rate_limit_chat_messages_per_day = 5
    low_limits.rate_limit_anonymous_chat_messages_per_day = 1
    captured = (await _capture(client)).json()
    assert (await client.post("/api/v1/chat", json=_chat_payload(captured), headers=API_KEY)).status_code == 200
    assert (await client.post("/api/v1/chat", json=_chat_payload(captured), headers=API_KEY)).status_code == 429


async def test_global_chat_cap_blocks_everyone_with_the_capacity_message(
    client: AsyncClient, db_session: AsyncSession, low_limits
) -> None:
    captured = (await _capture(client)).json()
    low_limits.global_chat_messages_per_day = 3
    await _seed_events(db_session, "ip:10.0.0.1", "chat", T0, T0, T0)  # other people's chats today

    blocked = await client.post("/api/v1/chat", json=_chat_payload(captured), headers=API_KEY)
    assert blocked.status_code == 429
    assert blocked.headers["X-Limit-Kind"] == "global"
    assert blocked.json()["detail"] == GLOBAL_CAPACITY_MESSAGE
    assert int(blocked.headers["Retry-After"]) == 12 * 3600


async def test_yesterdays_chats_do_not_count_towards_the_global_chat_cap(
    client: AsyncClient, db_session: AsyncSession, low_limits
) -> None:
    captured = (await _capture(client)).json()
    low_limits.global_chat_messages_per_day = 3
    yesterday = T0 - timedelta(days=1)
    await _seed_events(db_session, "ip:10.0.0.1", "chat", yesterday, yesterday, yesterday)
    assert (await client.post("/api/v1/chat", json=_chat_payload(captured), headers=API_KEY)).status_code == 200


async def test_admin_chat_ignores_and_is_not_counted_in_the_global_chat_cap(
    client: AsyncClient, db_session: AsyncSession, low_limits
) -> None:
    low_limits.admin_emails = "boss@example.com"
    headers, user_id = await _sign_in(db_session, "boss@example.com")
    captured = (await _capture(client, headers)).json()
    low_limits.global_chat_messages_per_day = 1
    await _seed_events(db_session, "ip:10.0.0.1", "chat", T0, T0)  # cap already exceeded for everyone else

    assert (await client.post("/api/v1/chat", json=_chat_payload(captured), headers=headers)).status_code == 200
    counted = await db_session.execute(
        select(func.count()).select_from(RateLimitEvent).where(RateLimitEvent.key == f"user:{user_id}", RateLimitEvent.action == "chat")
    )
    assert counted.scalar_one() == 0
