"""GET /usage (read-only counter), usage/cost events, POST /waitlist, and
account deletion for the new tables."""

import io
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_slide_analyzer
from app.core import clock
from app.core.config import get_settings
from app.main import app
from app.models.orm import ProWaitlistClick, RateLimitEvent, UsageEvent, User
from app.models.orm import Session as SessionRow
from app.services.slide_analyzer import PlaceholderSlideAnalyzer
from app.services.usage import record_usage

T0 = datetime(2026, 10, 10, 10, 0, tzinfo=UTC)  # 12:00 Africa/Johannesburg
API_KEY = {"X-API-Key": "test-api-key"}


@pytest.fixture(autouse=True)
def fixed_environment(monkeypatch):
    monkeypatch.setattr(clock, "now", lambda: T0)
    settings = get_settings()
    original = (
        settings.rate_limit_captures_per_day,
        settings.rate_limit_captures_per_month,
        settings.rate_limit_chat_messages_per_day,
        settings.global_captures_per_day,
        settings.admin_emails,
    )
    settings.rate_limit_captures_per_day = 20
    settings.rate_limit_captures_per_month = 400
    settings.rate_limit_chat_messages_per_day = 100
    settings.global_captures_per_day = 250
    settings.admin_emails = ""
    yield settings
    (
        settings.rate_limit_captures_per_day,
        settings.rate_limit_captures_per_month,
        settings.rate_limit_chat_messages_per_day,
        settings.global_captures_per_day,
        settings.admin_emails,
    ) = original


def _png(color: str = "white") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (10, 10), color=color).save(buffer, format="PNG")
    return buffer.getvalue()


async def _capture(client: AsyncClient, headers: dict[str, str] | None = None, color: str = "white") -> dict:
    response = await client.post(
        "/api/v1/slides/analyze",
        files={"image": ("slide.png", _png(color), "image/png")},
        data={"slide_number": "1"},
        headers=headers or API_KEY,
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _sign_in(db_session: AsyncSession, email: str) -> tuple[dict[str, str], uuid.UUID]:
    user = User(id=uuid.uuid4(), google_sub=f"sub-{email}", email=email)
    db_session.add(user)
    await db_session.flush()
    token = f"token-{email}"
    db_session.add(SessionRow(id=uuid.uuid4(), user_id=user.id, token=token, expires_at=T0 + timedelta(days=1)))
    await db_session.commit()
    return {**API_KEY, "Authorization": f"Bearer {token}"}, user.id


# --- /usage -----------------------------------------------------------------


async def test_usage_reports_limits_counts_and_reset_times(client: AsyncClient) -> None:
    before = (await client.get("/api/v1/usage", headers=API_KEY)).json()
    assert before["signed_in"] is False
    assert before["is_admin"] is False
    assert before["captures_today"] == {"used": 0, "limit": 20, "resets_at": "2026-10-10T22:00:00Z"}
    assert before["captures_month"]["limit"] == 400
    assert before["captures_month"]["resets_at"] == "2026-10-31T22:00:00Z"  # the 1st, 00:00 local
    assert before["chat_today"]["limit"] == 100
    assert before["global_blocked"] is False

    await _capture(client)
    await _capture(client, color="black")
    after = (await client.get("/api/v1/usage", headers=API_KEY)).json()
    assert after["captures_today"]["used"] == 2
    assert after["captures_month"]["used"] == 2


async def test_usage_is_read_only(client: AsyncClient, db_session: AsyncSession) -> None:
    await _capture(client)
    for _ in range(5):
        await client.get("/api/v1/usage", headers=API_KEY)
    events = (await db_session.execute(select(func.count()).select_from(RateLimitEvent))).scalar_one()
    assert events == 1


async def test_usage_follows_the_signed_in_user_not_the_ip(client: AsyncClient, db_session: AsyncSession) -> None:
    headers, _ = await _sign_in(db_session, "student@example.com")
    await _capture(client)  # anonymous
    await _capture(client, headers)
    await _capture(client, headers, color="black")

    anonymous = (await client.get("/api/v1/usage", headers=API_KEY)).json()
    signed_in = (await client.get("/api/v1/usage", headers=headers)).json()
    assert anonymous["captures_today"]["used"] == 1
    assert signed_in["captures_today"]["used"] == 2
    assert signed_in["signed_in"] is True


async def test_usage_flags_admins_as_unlimited_and_global_block(
    client: AsyncClient, db_session: AsyncSession, fixed_environment
) -> None:
    fixed_environment.admin_emails = "boss@example.com"
    fixed_environment.global_captures_per_day = 2
    db_session.add_all([RateLimitEvent(key="ip:9.9.9.9", action="analyze", created_at=T0) for _ in range(2)])
    await db_session.commit()
    admin_headers, _ = await _sign_in(db_session, "boss@example.com")

    admin = (await client.get("/api/v1/usage", headers=admin_headers)).json()
    assert admin["is_admin"] is True and admin["unlimited"] is True
    assert admin["global_blocked"] is False

    assert (await client.get("/api/v1/usage", headers=API_KEY)).json()["global_blocked"] is True


# --- usage / cost events ----------------------------------------------------


class _TokenReportingAnalyzer(PlaceholderSlideAnalyzer):
    model_name = "claude-haiku-5-5"

    async def analyze(self, image_bytes: bytes):
        record_usage(1000, 500)  # the main call
        record_usage(200, 100)  # a graph-localization call
        return await super().analyze(image_bytes)


async def test_capture_records_tokens_cost_and_cache_hit(client: AsyncClient, db_session: AsyncSession) -> None:
    app.dependency_overrides[get_slide_analyzer] = lambda: _TokenReportingAnalyzer()
    first = await _capture(client)
    await _capture(client)  # identical image: served from the cache, no model call

    events = (
        await db_session.execute(select(UsageEvent).where(UsageEvent.action == "analyze").order_by(UsageEvent.id))
    ).scalars().all()
    by_hit = {event.cache_hit: event for event in events}
    fresh, cached = by_hit[False], by_hit[True]
    assert (fresh.input_tokens, fresh.output_tokens) == (1200, 600)
    # $0.10/M in + $0.50/M out: (1200 * 0.10 + 600 * 0.50) / 1e6
    assert fresh.est_cost_usd == pytest.approx(0.00042)
    assert fresh.model == "claude-haiku-5-5"
    assert str(fresh.slide_id) == first["slide_id"]
    assert (cached.input_tokens, cached.output_tokens, cached.est_cost_usd) == (0, 0, 0)


async def test_chat_records_the_providers_reported_tokens(client: AsyncClient, db_session: AsyncSession) -> None:
    headers, user_id = await _sign_in(db_session, "chatter@example.com")
    captured = await _capture(client, headers)
    await client.post(
        "/api/v1/chat",
        json={
            "conversation_id": None,
            "presentation_id": captured["presentation_id"],
            "query_mode": "slide",
            "slide_id": captured["slide_id"],
            "object_id": None,
            "message": "hello",
        },
        headers=headers,
    )
    event = (await db_session.execute(select(UsageEvent).where(UsageEvent.action == "chat"))).scalar_one()
    assert (event.input_tokens, event.output_tokens) == (10, 2)  # FakeChatService's usage
    assert event.user_id == user_id
    assert event.conversation_id is not None


# --- waitlist ---------------------------------------------------------------


async def test_waitlist_requires_sign_in(client: AsyncClient) -> None:
    response = await client.post("/api/v1/waitlist", json={"source": "daily"}, headers=API_KEY)
    assert response.status_code == 401


async def test_waitlist_counts_every_click_and_the_user_behind_it(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    headers, user_id = await _sign_in(db_session, "interested@example.com")
    for source in ("daily", "daily", "monthly"):
        response = await client.post("/api/v1/waitlist", json={"source": source}, headers=headers)
        assert response.json() == {"joined": True}

    clicks = (await db_session.execute(select(ProWaitlistClick))).scalars().all()
    assert len(clicks) == 3
    assert {click.user_id for click in clicks} == {user_id}


async def test_waitlist_rejects_an_unknown_source(client: AsyncClient, db_session: AsyncSession) -> None:
    headers, _ = await _sign_in(db_session, "x@example.com")
    assert (await client.post("/api/v1/waitlist", json={"source": "spam"}, headers=headers)).status_code == 422


# --- account deletion -------------------------------------------------------


async def test_deleting_an_account_anonymises_spend_and_removes_the_waitlist_rows(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    headers, _ = await _sign_in(db_session, "leaving@example.com")
    await _capture(client, headers)
    await client.post("/api/v1/waitlist", json={"source": "settings"}, headers=headers)
    spend_rows = (await db_session.execute(select(func.count()).select_from(UsageEvent))).scalar_one()

    assert (await client.delete("/api/v1/auth/account", headers=headers)).status_code == 204

    # Spend history survives, with no user attached; the waitlist click is gone.
    assert (await db_session.execute(select(func.count()).select_from(UsageEvent))).scalar_one() == spend_rows
    assert (await db_session.execute(select(UsageEvent.user_id))).scalars().all() == [None] * spend_rows
    assert (await db_session.execute(select(func.count()).select_from(ProWaitlistClick))).scalar_one() == 0
