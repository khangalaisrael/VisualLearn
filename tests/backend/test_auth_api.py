"""POST /auth/google, POST /auth/logout (docs/PublicHostingMVP.md Phase 2).

Never calls Google's real userinfo endpoint — `app.services.google_oauth
.verify_google_access_token` is monkeypatched per test, the same way
tests/backend/conftest.py's `client` fixture keeps every other test off
real provider APIs."""

import pytest

from app.api.v1 import auth as auth_router
from app.services import google_oauth


@pytest.fixture
def mock_google_user(monkeypatch):
    """Returns a setter: call it with (sub, email) to make the next
    verify_google_access_token call succeed with that identity. Not called
    at all -> verify_google_access_token raises (simulates an invalid
    token), matching what a real bad/expired access token does."""

    async def _default_raises(access_token: str):
        del access_token
        raise google_oauth.GoogleTokenVerificationError("no mock identity configured for this test")

    state = {"fn": _default_raises}

    async def _dispatch(access_token: str):
        return await state["fn"](access_token)

    # Patched where it's *used* (app.api.v1.auth imported it by name via
    # `from ... import verify_google_access_token`, so that module's own
    # binding is what actually runs — patching google_oauth's attribute
    # alone wouldn't reach it).
    monkeypatch.setattr(auth_router, "verify_google_access_token", _dispatch)

    def _set(sub: str, email: str | None = "student@example.com") -> None:
        async def _succeeds(access_token: str):
            del access_token
            return google_oauth.GoogleUserInfo(sub=sub, email=email)

        state["fn"] = _succeeds

    return _set


async def test_sign_in_creates_user_and_returns_session_token(client, mock_google_user) -> None:
    mock_google_user("google-sub-123", "student@example.com")

    response = await client.post(
        "/api/v1/auth/google",
        json={"access_token": "fake-google-access-token"},
        headers={"X-API-Key": "test-api-key"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "student@example.com"
    assert len(body["session_token"]) > 20


async def test_sign_in_twice_reuses_the_same_user(client, mock_google_user) -> None:
    mock_google_user("google-sub-123", "student@example.com")

    first = await client.post(
        "/api/v1/auth/google", json={"access_token": "t1"}, headers={"X-API-Key": "test-api-key"}
    )
    second = await client.post(
        "/api/v1/auth/google", json={"access_token": "t2"}, headers={"X-API-Key": "test-api-key"}
    )

    assert first.status_code == 200
    assert second.status_code == 200
    # Same Google account -> same user, but each sign-in still gets its own
    # session token (e.g. signing in on two devices shouldn't invalidate
    # the other one).
    assert first.json()["session_token"] != second.json()["session_token"]


async def test_sign_in_rejects_invalid_google_token(client, mock_google_user) -> None:
    del mock_google_user  # fixture's default (no identity set) already raises

    response = await client.post(
        "/api/v1/auth/google",
        json={"access_token": "not-a-real-token"},
        headers={"X-API-Key": "test-api-key"},
    )

    assert response.status_code == 401


async def test_sign_in_requires_local_api_key(client, mock_google_user) -> None:
    mock_google_user("google-sub-123")

    response = await client.post("/api/v1/auth/google", json={"access_token": "t"})

    assert response.status_code == 401


async def test_logout_invalidates_the_session_token(client, mock_google_user) -> None:
    mock_google_user("google-sub-123")

    signed_in = await client.post(
        "/api/v1/auth/google", json={"access_token": "t"}, headers={"X-API-Key": "test-api-key"}
    )
    session_token = signed_in.json()["session_token"]

    logout_response = await client.post(
        "/api/v1/auth/logout",
        json={"session_token": session_token},
        headers={"X-API-Key": "test-api-key"},
    )

    assert logout_response.status_code == 204


async def test_logout_is_idempotent_for_an_unknown_token(client) -> None:
    # Logging out twice (or with a token that was never valid) must not
    # error — there's nothing meaningfully wrong with "already signed out".
    response = await client.post(
        "/api/v1/auth/logout",
        json={"session_token": "never-existed"},
        headers={"X-API-Key": "test-api-key"},
    )

    assert response.status_code == 204
