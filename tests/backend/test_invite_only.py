"""Invite-only mode (ALLOWED_EMAILS): only listed Google accounts and admins can sign in,
capture or chat. Empty list = open to everyone, exactly as before."""

import io
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1 import auth as auth_router
from app.core.config import get_settings
from app.models.orm import RateLimitEvent, User
from app.models.orm import Session as SessionRow
from app.services import google_oauth

API_KEY = {"X-API-Key": "test-api-key"}


@pytest.fixture(autouse=True)
def invite_settings():
    settings = get_settings()
    original = (settings.allowed_emails, settings.admin_emails, settings.privacy_contact_email)
    settings.allowed_emails = ""
    settings.admin_emails = ""
    settings.privacy_contact_email = "help@example.com"
    yield settings
    settings.allowed_emails, settings.admin_emails, settings.privacy_contact_email = original


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


async def _sign_in(db: AsyncSession, email: str) -> dict[str, str]:
    user = User(id=uuid.uuid4(), google_sub=f"sub-{email}", email=email)
    db.add(user)
    await db.flush()
    db.add(SessionRow(id=uuid.uuid4(), user_id=user.id, token=f"token-{email}", expires_at=datetime.now(UTC) + timedelta(days=1)))
    await db.commit()
    return {**API_KEY, "Authorization": f"Bearer token-{email}"}


def _chat_payload(captured: dict) -> dict:
    return {
        "conversation_id": None,
        "presentation_id": captured["presentation_id"],
        "query_mode": "slide",
        "slide_id": captured["slide_id"],
        "object_id": None,
        "message": "Explain this.",
    }


# --- open mode is unchanged ----------------------------------------------------------------


async def test_without_a_list_everyone_can_use_it(client: AsyncClient, db_session: AsyncSession) -> None:
    assert (await _capture(client)).status_code == 200  # signed out
    assert (await _capture(client, await _sign_in(db_session, "anyone@example.com"))).status_code == 200
    usage = (await client.get("/api/v1/usage", headers=API_KEY)).json()
    assert usage["invite_only"] is False and usage["allowed"] is True


# --- invite-only -------------------------------------------------------------------------------


async def test_signed_out_visitors_are_turned_away(client: AsyncClient, invite_settings) -> None:
    invite_settings.allowed_emails = "friend@example.com"
    blocked = await _capture(client)
    assert blocked.status_code == 403
    assert blocked.headers["X-Access"] == "invite-only"
    assert "invite-only" in blocked.json()["detail"]
    assert "help@example.com" in blocked.json()["detail"]


async def test_a_signed_in_account_that_is_not_listed_is_turned_away(
    client: AsyncClient, db_session: AsyncSession, invite_settings
) -> None:
    invite_settings.allowed_emails = "friend@example.com"
    stranger = await _sign_in(db_session, "stranger@example.com")
    assert (await _capture(client, stranger)).status_code == 403


async def test_a_listed_account_works_whatever_the_capitalisation(
    client: AsyncClient, db_session: AsyncSession, invite_settings
) -> None:
    invite_settings.allowed_emails = " Friend@Example.com , other@example.com "
    friend = await _sign_in(db_session, "friend@example.com")
    assert (await _capture(client, friend)).status_code == 200


async def test_admins_are_always_allowed(client: AsyncClient, db_session: AsyncSession, invite_settings) -> None:
    invite_settings.allowed_emails = "friend@example.com"
    invite_settings.admin_emails = "boss@example.com"
    boss = await _sign_in(db_session, "boss@example.com")
    assert (await _capture(client, boss)).status_code == 200


async def test_chat_is_gated_too(client: AsyncClient, db_session: AsyncSession, invite_settings) -> None:
    friend = await _sign_in(db_session, "friend@example.com")
    captured = (await _capture(client, friend)).json()  # open mode so far: fine

    invite_settings.allowed_emails = "someone-else@example.com"  # the friend is no longer on the list
    assert (await client.post("/api/v1/chat", json=_chat_payload(captured), headers=friend)).status_code == 403
    assert (await client.post("/api/v1/chat", json=_chat_payload(captured), headers=API_KEY)).status_code == 403

    invite_settings.allowed_emails = "friend@example.com"
    assert (await client.post("/api/v1/chat", json=_chat_payload(captured), headers=friend)).status_code == 200


async def test_a_turned_away_request_is_not_counted_against_anyone(
    client: AsyncClient, invite_settings, db_session: AsyncSession
) -> None:
    invite_settings.allowed_emails = "friend@example.com"
    for _ in range(3):
        assert (await _capture(client)).status_code == 403
    count = (await db_session.execute(select(func.count()).select_from(RateLimitEvent))).scalar_one()
    assert count == 0


async def test_usage_tells_the_extension_who_is_allowed(
    client: AsyncClient, db_session: AsyncSession, invite_settings
) -> None:
    invite_settings.allowed_emails = "friend@example.com"
    signed_out = (await client.get("/api/v1/usage", headers=API_KEY)).json()
    assert (signed_out["invite_only"], signed_out["allowed"]) == (True, False)
    assert signed_out["invite_contact"] == "help@example.com"

    stranger = await _sign_in(db_session, "stranger@example.com")
    assert (await client.get("/api/v1/usage", headers=stranger)).json()["allowed"] is False

    friend = await _sign_in(db_session, "friend@example.com")
    assert (await client.get("/api/v1/usage", headers=friend)).json()["allowed"] is True


# --- signing in -----------------------------------------------------------------------------------


@pytest.fixture
def google_identity(monkeypatch):
    async def _fake(identity: dict):
        async def _verify(access_token: str):
            del access_token
            return google_oauth.GoogleUserInfo(sub=identity["sub"], email=identity["email"])

        return _verify

    holder: dict = {}

    async def _dispatch(access_token: str):
        return await (await _fake(holder))(access_token)

    monkeypatch.setattr(auth_router, "verify_google_access_token", _dispatch)

    def _set(sub: str, email: str) -> None:
        holder["sub"], holder["email"] = sub, email

    return _set


async def _sign_in_request(client: AsyncClient):
    return await client.post("/api/v1/auth/google", json={"access_token": "x"}, headers=API_KEY)


async def test_signing_in_with_an_unlisted_account_is_refused_and_creates_nothing(
    client: AsyncClient, db_session: AsyncSession, invite_settings, google_identity
) -> None:
    invite_settings.allowed_emails = "friend@example.com"
    google_identity("sub-stranger", "stranger@example.com")
    refused = await _sign_in_request(client)
    assert refused.status_code == 403
    assert refused.headers["X-Access"] == "invite-only"
    assert (await db_session.execute(select(func.count()).select_from(User))).scalar_one() == 0
    assert (await db_session.execute(select(func.count()).select_from(SessionRow))).scalar_one() == 0


async def test_signing_in_with_a_listed_account_or_an_admin_works(
    client: AsyncClient, invite_settings, google_identity
) -> None:
    invite_settings.allowed_emails = "friend@example.com"
    invite_settings.admin_emails = "boss@example.com"

    google_identity("sub-friend", "Friend@example.com")
    assert (await _sign_in_request(client)).status_code == 200

    google_identity("sub-boss", "boss@example.com")
    assert (await _sign_in_request(client)).status_code == 200


async def test_anyone_can_sign_in_when_there_is_no_list(client: AsyncClient, google_identity) -> None:
    google_identity("sub-anyone", "anyone@example.com")
    assert (await _sign_in_request(client)).status_code == 200


# --- the public pages ---------------------------------------------------------------------------------


async def test_the_home_page_says_invite_only_when_it_is(client: AsyncClient, invite_settings) -> None:
    invite_settings.allowed_emails = "friend@example.com"
    home = (await client.get("/")).text
    assert "Invite-only beta" in home and "invite-only while it's in beta" in home
    assert "help@example.com" in home
    assert "invite-only right now" in (await client.get("/install")).text

    invite_settings.allowed_emails = ""
    assert "Invite-only beta" not in (await client.get("/")).text
