"""Phase 3 — multi-tenant data isolation (docs/PublicHostingMVP.md).

One user's presentations (and everything scoped under them — slides,
chat) must be invisible to every other user, while the pre-Phase-3
anonymous/local-first flow (nobody signed in at all) keeps working
exactly as before. These are privacy-correctness tests, not just
happy-path coverage — a bug here is a real privacy incident.
"""

import io
import uuid
from datetime import datetime, timedelta, timezone

from httpx import AsyncClient
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orm import Session as SessionRow
from app.models.orm import User


def _fake_png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (10, 10), color="white").save(buffer, format="PNG")
    return buffer.getvalue()


async def _create_signed_in_user(db_session: AsyncSession, *, email: str) -> str:
    """Creates a User + a valid Session row directly (bypassing the real
    Google OAuth round-trip, which test_auth_api.py already covers) and
    returns the bearer token to send as `Authorization: Bearer <token>`."""
    user = User(id=uuid.uuid4(), google_sub=f"sub-{email}", email=email)
    db_session.add(user)
    await db_session.flush()

    token = f"test-session-token-{email}"
    session = SessionRow(
        id=uuid.uuid4(),
        user_id=user.id,
        token=token,
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    db_session.add(session)
    await db_session.commit()
    return token


async def _capture(client: AsyncClient, *, presentation_id: str | None = None, token: str | None = None) -> dict:
    headers = {"X-API-Key": "test-api-key"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = {"slide_number": "1"}
    if presentation_id:
        data["presentation_id"] = presentation_id
    response = await client.post(
        "/api/v1/slides/analyze",
        files={"image": ("slide.png", _fake_png_bytes(), "image/png")},
        data=data,
        headers=headers,
    )
    return {"status": response.status_code, "body": response.json()}


async def test_owners_own_presentation_is_accessible_to_them(client: AsyncClient, db_session: AsyncSession) -> None:
    token = await _create_signed_in_user(db_session, email="alex@example.com")

    created = await _capture(client, token=token)
    assert created["status"] == 200

    reused = await _capture(client, presentation_id=created["body"]["presentation_id"], token=token)
    assert reused["status"] == 200


async def test_a_different_signed_in_user_cannot_access_someone_elses_presentation(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    owner_token = await _create_signed_in_user(db_session, email="owner@example.com")
    other_token = await _create_signed_in_user(db_session, email="other@example.com")

    created = await _capture(client, token=owner_token)
    presentation_id = created["body"]["presentation_id"]

    blocked = await _capture(client, presentation_id=presentation_id, token=other_token)
    assert blocked["status"] == 404


async def test_an_anonymous_request_cannot_access_a_signed_in_users_presentation(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    owner_token = await _create_signed_in_user(db_session, email="owner2@example.com")

    created = await _capture(client, token=owner_token)
    presentation_id = created["body"]["presentation_id"]

    blocked = await _capture(client, presentation_id=presentation_id, token=None)
    assert blocked["status"] == 404


async def test_anonymous_presentations_remain_open_to_anyone(client: AsyncClient, db_session: AsyncSession) -> None:
    """Backward compatibility: a presentation created before Phase 2/3 (or
    by a request that simply never signed in) has user_id=None and must
    stay accessible the way the whole local-first flow always worked —
    isolation only kicks in once something is actually owned."""
    created = await _capture(client, token=None)
    presentation_id = created["body"]["presentation_id"]

    reused_anonymously = await _capture(client, presentation_id=presentation_id, token=None)
    assert reused_anonymously["status"] == 200

    signed_in_token = await _create_signed_in_user(db_session, email="curious@example.com")
    reused_signed_in = await _capture(client, presentation_id=presentation_id, token=signed_in_token)
    assert reused_signed_in["status"] == 200


async def test_an_invalid_bearer_token_is_rejected_outright(client: AsyncClient) -> None:
    # Not silently treated as anonymous — a forged/expired token must fail
    # loudly (see get_current_user_id's docstring for why).
    result = await _capture(client, token="not-a-real-session-token")
    assert result["status"] == 401


async def test_chat_also_enforces_presentation_ownership(client: AsyncClient, db_session: AsyncSession) -> None:
    owner_token = await _create_signed_in_user(db_session, email="chatowner@example.com")
    other_token = await _create_signed_in_user(db_session, email="chatother@example.com")

    created = await _capture(client, token=owner_token)
    presentation_id = created["body"]["presentation_id"]
    slide_id = created["body"]["slide_id"]

    blocked = await client.post(
        "/api/v1/chat",
        json={
            "conversation_id": None,
            "presentation_id": presentation_id,
            "query_mode": "slide",
            "slide_id": slide_id,
            "object_id": None,
            "message": "What is this slide about?",
        },
        headers={"X-API-Key": "test-api-key", "Authorization": f"Bearer {other_token}"},
    )
    assert blocked.status_code == 404

    allowed = await client.post(
        "/api/v1/chat",
        json={
            "conversation_id": None,
            "presentation_id": presentation_id,
            "query_mode": "slide",
            "slide_id": slide_id,
            "object_id": None,
            "message": "What is this slide about?",
        },
        headers={"X-API-Key": "test-api-key", "Authorization": f"Bearer {owner_token}"},
    )
    assert allowed.status_code == 200
