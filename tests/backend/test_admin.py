"""Admin dashboard endpoints: access control, overview numbers, per-user
spend with outlier flags, and waitlist demand."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.core.config import get_settings
from app.models.orm import ProWaitlistClick, UsageEvent, User
from app.models.orm import Session as SessionRow
from app.services.admin_stats import outlier_ids

T0 = datetime(2026, 10, 10, 10, 0, tzinfo=UTC)  # 12:00 Africa/Johannesburg
API_KEY = {"X-API-Key": "test-api-key"}
ADMIN_EMAIL = "owner@example.com"


@pytest.fixture(autouse=True)
def fixed_environment(monkeypatch):
    monkeypatch.setattr(clock, "now", lambda: T0)
    settings = get_settings()
    original = (settings.admin_emails, settings.global_captures_per_day)
    settings.admin_emails = ADMIN_EMAIL
    settings.global_captures_per_day = 250
    yield
    settings.admin_emails, settings.global_captures_per_day = original


async def _sign_in(db: AsyncSession, email: str) -> tuple[dict[str, str], uuid.UUID]:
    user = User(id=uuid.uuid4(), google_sub=f"sub-{email}", email=email)
    db.add(user)
    await db.flush()
    db.add(SessionRow(id=uuid.uuid4(), user_id=user.id, token=f"token-{email}", expires_at=T0 + timedelta(days=1)))
    await db.commit()
    return {**API_KEY, "Authorization": f"Bearer token-{email}"}, user.id


def _event(user_id, action="analyze", cost=0.001, when=T0 - timedelta(hours=1), tokens=(3000, 800)) -> UsageEvent:
    return UsageEvent(
        user_id=user_id,
        action=action,
        model="claude-haiku-5-5",
        input_tokens=tokens[0],
        output_tokens=tokens[1],
        est_cost_usd=cost,
        created_at=when,
    )


# --- access -------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/api/v1/admin/overview", "/api/v1/admin/users", "/api/v1/admin/waitlist"])
async def test_admin_endpoints_are_for_admins_only(client: AsyncClient, db_session: AsyncSession, path: str) -> None:
    student, _ = await _sign_in(db_session, "student@example.com")
    admin, _ = await _sign_in(db_session, ADMIN_EMAIL)

    assert (await client.get(path)).status_code == 401  # no API key
    assert (await client.get(path, headers=API_KEY)).status_code == 403  # signed out
    assert (await client.get(path, headers=student)).status_code == 403  # signed in, not admin
    assert (await client.get(path, headers=admin)).status_code == 200


# --- overview ----------------------------------------------------------------


async def test_overview_counts_today_month_and_series(client: AsyncClient, db_session: AsyncSession) -> None:
    admin, _ = await _sign_in(db_session, ADMIN_EMAIL)
    _, alex = await _sign_in(db_session, "alex@example.com")
    _, sam = await _sign_in(db_session, "sam@example.com")
    db_session.add_all(
        [
            _event(alex, cost=0.002),
            _event(alex, "chat", cost=0.001),
            _event(sam, cost=0.004),
            _event(sam, "limit_hit_daily", cost=0.0),
            _event(sam, cost=0.010, when=T0 - timedelta(days=3)),  # earlier this month
            _event(sam, cost=0.100, when=T0 - timedelta(days=40)),  # outside every window
        ]
    )
    await db_session.commit()

    body = (await client.get("/api/v1/admin/overview", headers=admin)).json()
    assert body["timezone"] == "Africa/Johannesburg"
    assert body["global_cap"] == 250
    assert body["cost_today_usd"] == pytest.approx(0.007)
    assert body["cost_month_usd"] == pytest.approx(0.017)  # since the 1st
    assert body["cost_30d_usd"] == pytest.approx(0.017)
    assert body["active_users_today"] == 2
    assert body["limit_hits_today"] == 1
    assert body["total_users"] == 3

    days = body["days"]
    assert len(days) == 14
    assert days[-1]["date"] == "2026-10-10"
    assert (days[-1]["captures"], days[-1]["chats"]) == (2, 1)
    assert days[-4]["date"] == "2026-10-07" and days[-4]["captures"] == 1


async def test_overview_waitlist_and_global_cap_counts(client: AsyncClient, db_session: AsyncSession) -> None:
    admin, _ = await _sign_in(db_session, ADMIN_EMAIL)
    _, alex = await _sign_in(db_session, "alex@example.com")
    db_session.add_all(
        [
            ProWaitlistClick(user_id=alex, source="daily"),
            ProWaitlistClick(user_id=alex, source="monthly"),
        ]
    )
    await db_session.commit()
    body = (await client.get("/api/v1/admin/overview", headers=admin)).json()
    assert (body["waitlist_clicks"], body["waitlist_users"]) == (2, 1)
    assert body["global_captures_today"] == 0


# --- users and outliers ----------------------------------------------------------


def test_outlier_needs_three_spenders_and_a_real_gap() -> None:
    assert outlier_ids({"a": 0.5, "b": 0.01}) == set()  # too few to call anyone typical
    assert outlier_ids({"a": 0.30, "b": 0.012, "c": 0.01, "d": 0.0}) == {"a"}
    assert outlier_ids({"a": 0.003, "b": 0.001, "c": 0.001}) == set()  # a fraction of a cent isn't a problem
    assert outlier_ids({"a": 0.02, "b": 0.019, "c": 0.021}) == set()  # everyone similar


async def test_users_lists_spend_tokens_and_flags_the_outlier(client: AsyncClient, db_session: AsyncSession) -> None:
    admin, _ = await _sign_in(db_session, ADMIN_EMAIL)
    _, heavy = await _sign_in(db_session, "heavy@example.com")
    _, a = await _sign_in(db_session, "a@example.com")
    _, b = await _sign_in(db_session, "b@example.com")
    _, idle = await _sign_in(db_session, "idle@example.com")
    db_session.add_all(
        [_event(heavy, cost=0.05) for _ in range(6)]
        + [_event(a, cost=0.012), _event(b, cost=0.010), _event(heavy, "limit_hit_daily", cost=0.0)]
    )
    await db_session.commit()

    body = (await client.get("/api/v1/admin/users", headers=admin)).json()
    by_email = {u["email"]: u for u in body["users"]}
    assert body["users"][0]["email"] == "heavy@example.com"  # sorted by spend
    assert by_email["heavy@example.com"]["captures_30d"] == 6
    assert by_email["heavy@example.com"]["cost_30d_usd"] == pytest.approx(0.30)
    assert by_email["heavy@example.com"]["input_tokens"] == 6 * 3000
    assert by_email["heavy@example.com"]["limit_hits_30d"] == 1
    assert by_email["heavy@example.com"]["is_outlier"] is True
    assert by_email["a@example.com"]["is_outlier"] is False
    assert by_email["idle@example.com"]["captures_30d"] == 0  # signed up, never captured
    assert by_email["idle@example.com"]["last_active"] is None
    assert body["median_cost_usd"] == pytest.approx(0.012)


async def test_signed_out_and_deleted_usage_is_pooled(client: AsyncClient, db_session: AsyncSession) -> None:
    admin, _ = await _sign_in(db_session, ADMIN_EMAIL)
    db_session.add_all([_event(None, cost=0.003), _event(None, cost=0.002)])
    await db_session.commit()
    users = (await client.get("/api/v1/admin/users", headers=admin)).json()["users"]
    pooled = [u for u in users if u["user_id"] is None]
    assert len(pooled) == 1
    assert (pooled[0]["captures_30d"], pooled[0]["cost_30d_usd"]) == (2, pytest.approx(0.005))


# --- waitlist ----------------------------------------------------------------


async def test_waitlist_groups_clicks_by_person(client: AsyncClient, db_session: AsyncSession) -> None:
    admin, _ = await _sign_in(db_session, ADMIN_EMAIL)
    _, alex = await _sign_in(db_session, "alex@example.com")
    _, sam = await _sign_in(db_session, "sam@example.com")
    db_session.add_all(
        [
            ProWaitlistClick(user_id=alex, source="daily", created_at=T0 - timedelta(days=2)),
            ProWaitlistClick(user_id=alex, source="monthly", created_at=T0 - timedelta(hours=1)),
            ProWaitlistClick(user_id=sam, source="settings", created_at=T0 - timedelta(days=1)),
        ]
    )
    await db_session.commit()

    body = (await client.get("/api/v1/admin/waitlist", headers=admin)).json()
    assert (body["unique_users"], body["total_clicks"]) == (2, 3)
    assert [e["email"] for e in body["entries"]] == ["alex@example.com", "sam@example.com"]  # latest first
    alex_entry = body["entries"][0]
    assert alex_entry["clicks"] == 2
    assert alex_entry["sources"] == ["daily", "monthly"]
    assert alex_entry["first_click"] < alex_entry["last_click"]
