"""Chat history (GET/DELETE /conversations) and retention cleanup."""

import io
import uuid
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from PIL import Image
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orm import Conversation, Message, Presentation, RateLimitEvent, Slide, User
from app.models.orm import Session as SessionRow

API_KEY = {"X-API-Key": "test-api-key"}


def _png(color: str = "white") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (10, 10), color=color).save(buffer, format="PNG")
    return buffer.getvalue()


async def _sign_in(db_session: AsyncSession, email: str) -> dict[str, str]:
    user = User(id=uuid.uuid4(), google_sub=f"sub-{email}", email=email)
    db_session.add(user)
    await db_session.flush()
    token = f"token-{email}"
    db_session.add(
        SessionRow(id=uuid.uuid4(), user_id=user.id, token=token, expires_at=datetime.now(UTC) + timedelta(days=1))
    )
    await db_session.commit()
    return {**API_KEY, "Authorization": f"Bearer {token}"}


async def _capture_and_chat(client: AsyncClient, headers: dict[str, str], message: str = "What is this?") -> dict:
    captured = await client.post(
        "/api/v1/slides/analyze",
        files={"image": ("slide.png", _png(), "image/png")},
        data={"slide_number": "1"},
        headers=headers,
    )
    body = captured.json()
    chat = await client.post(
        "/api/v1/chat",
        json={
            "conversation_id": None,
            "presentation_id": body["presentation_id"],
            "query_mode": "slide",
            "slide_id": body["slide_id"],
            "object_id": None,
            "message": message,
        },
        headers=headers,
    )
    assert chat.status_code == 200
    conversation_id = chat.text.split('"conversation_id": "')[1].split('"')[0]
    return {**body, "conversation_id": conversation_id}


async def test_list_requires_sign_in(client: AsyncClient) -> None:
    response = await client.get("/api/v1/conversations", headers=API_KEY)
    assert response.status_code == 401


async def test_signed_in_user_sees_their_chat_with_its_slide_and_messages(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    headers = await _sign_in(db_session, "alex@example.com")
    created = await _capture_and_chat(client, headers, "Explain the main idea")

    listed = (await client.get("/api/v1/conversations", headers=headers)).json()
    assert listed["retention_days"] == 30
    assert [c["id"] for c in listed["conversations"]] == [created["conversation_id"]]
    assert listed["conversations"][0]["title"] == "Explain the main idea"

    detail = (await client.get(f"/api/v1/conversations/{created['conversation_id']}", headers=headers)).json()
    assert detail["slide"]["slide_id"] == created["slide_id"]
    assert len(detail["slide"]["objects"]) == len(created["objects"])
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assert detail["messages"][0]["content"] == "Explain the main idea"


async def test_another_user_cannot_list_open_or_delete_the_chat(client: AsyncClient, db_session: AsyncSession) -> None:
    owner = await _sign_in(db_session, "owner@example.com")
    other = await _sign_in(db_session, "other@example.com")
    created = await _capture_and_chat(client, owner)
    url = f"/api/v1/conversations/{created['conversation_id']}"

    assert (await client.get("/api/v1/conversations", headers=other)).json()["conversations"] == []
    assert (await client.get(url, headers=other)).status_code == 404
    assert (await client.delete(url, headers=other)).status_code == 404
    assert (await client.get(url, headers=owner)).status_code == 200


async def test_chat_cannot_continue_another_users_conversation(client: AsyncClient, db_session: AsyncSession) -> None:
    """The other user's messages would otherwise be fed to the model as
    history for the attacker's own presentation."""
    owner = await _sign_in(db_session, "owner2@example.com")
    other = await _sign_in(db_session, "other2@example.com")
    victim = await _capture_and_chat(client, owner)
    mine = await _capture_and_chat(client, other)

    response = await client.post(
        "/api/v1/chat",
        json={
            "conversation_id": victim["conversation_id"],
            "presentation_id": mine["presentation_id"],
            "query_mode": "slide",
            "slide_id": mine["slide_id"],
            "object_id": None,
            "message": "continue",
        },
        headers=other,
    )
    assert response.status_code == 404


async def test_owner_can_delete_a_chat(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _sign_in(db_session, "deleter@example.com")
    created = await _capture_and_chat(client, headers)

    deleted = await client.delete(f"/api/v1/conversations/{created['conversation_id']}", headers=headers)
    assert deleted.status_code == 204
    assert (await client.get("/api/v1/conversations", headers=headers)).json()["conversations"] == []
    remaining = await db_session.execute(select(Message))
    assert remaining.scalars().all() == []


async def test_expired_chat_is_hidden_then_removed_by_cleanup(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _sign_in(db_session, "old@example.com")
    old = await _capture_and_chat(client, headers, "old chat")
    long_ago = datetime.now(UTC) - timedelta(days=31)
    await db_session.execute(update(Conversation).values(last_activity_at=long_ago))
    await db_session.execute(update(Presentation).values(created_at=long_ago))
    await db_session.execute(update(Slide).values(created_at=long_ago))
    db_session.add(RateLimitEvent(key="ip:1.2.3.4", action="chat", created_at=long_ago))
    await db_session.commit()
    fresh = await _capture_and_chat(client, headers, "fresh chat")

    # Hidden on read before any cleanup has run.
    listed = (await client.get("/api/v1/conversations", headers=headers)).json()["conversations"]
    assert [c["id"] for c in listed] == [fresh["conversation_id"]]
    assert (await client.get(f"/api/v1/conversations/{old['conversation_id']}", headers=headers)).status_code == 404

    result = (await client.post("/api/v1/maintenance/cleanup", headers=API_KEY)).json()
    assert result["conversations"] == 1
    assert result["presentations"] == 1
    assert result["rate_limit_events"] == 1

    conversations = (await db_session.execute(select(Conversation.id))).scalars().all()
    presentations = (await db_session.execute(select(Presentation.id))).scalars().all()
    assert [str(c) for c in conversations] == [fresh["conversation_id"]]
    assert [str(p) for p in presentations] == [fresh["presentation_id"]]


async def test_cleanup_requires_api_key(client: AsyncClient) -> None:
    assert (await client.post("/api/v1/maintenance/cleanup")).status_code == 401
