"""General chat: POST /chat with query_mode "general", an open chat with no
slide behind it. It needs only a message, keeps a conversation like any
other chat, and cannot be used to continue someone else's or a slide's chat."""

import io
import uuid
from datetime import UTC, datetime, timedelta

from conftest import FakeChatService
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orm import Conversation, Message, UsageEvent, User
from app.models.orm import Session as SessionRow

API_KEY = {"X-API-Key": "test-api-key"}


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


async def _chat(client: AsyncClient, headers: dict[str, str], message: str, **fields):
    return await client.post(
        "/api/v1/chat",
        json={
            "conversation_id": None,
            "presentation_id": None,
            "query_mode": "general",
            "slide_id": None,
            "object_id": None,
            "message": message,
            **fields,
        },
        headers=headers,
    )


def _conversation_id(response) -> str:
    return response.text.split('"conversation_id": "')[1].split('"')[0]


async def test_general_chat_needs_only_a_message(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _sign_in(db_session, "a@example.com")
    response = await _chat(client, headers, "What is a monad?")
    assert response.status_code == 200, response.text
    assert "Fake " in response.text and "event: done" in response.text

    prompt = FakeChatService.captured_system_prompts[-1]
    assert prompt.startswith("You are VisionLearn, a STEM tutor for university students. This is an open chat")
    assert "<slide_data>" not in prompt and not prompt.endswith("\n")

    conversation = (await db_session.execute(select(Conversation))).scalar_one()
    assert (conversation.presentation_id, conversation.slide_id) == (None, None)
    assert conversation.title == "What is a monad?"
    modes = (await db_session.execute(select(Message.query_mode))).scalars().all()
    assert modes == ["general", "general"]
    assert "chat" in (await db_session.execute(select(UsageEvent.action))).scalars().all()


async def test_general_chat_continues_and_can_be_reopened(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _sign_in(db_session, "a@example.com")
    conversation_id = _conversation_id(await _chat(client, headers, "What is a monad?"))
    again = await _chat(client, headers, "Give an example", conversation_id=conversation_id)
    assert again.status_code == 200 and _conversation_id(again) == conversation_id
    assert len((await db_session.execute(select(Message.id))).scalars().all()) == 4

    reopened = (await client.get(f"/api/v1/conversations/{conversation_id}", headers=headers)).json()
    assert reopened["slide"] is None
    assert [m["content"] for m in reopened["messages"]] == ["What is a monad?", "Fake answer.", "Give an example", "Fake answer."]


async def test_general_chat_works_signed_out(client: AsyncClient) -> None:
    assert (await _chat(client, API_KEY, "What is a monad?")).status_code == 200


async def test_general_chat_cannot_continue_another_chat(client: AsyncClient, db_session: AsyncSession) -> None:
    alex = await _sign_in(db_session, "alex@example.com")
    sam = await _sign_in(db_session, "sam@example.com")
    alexs = _conversation_id(await _chat(client, alex, "Private question"))
    # Another account's chat, and a chat about a slide, are both off limits.
    assert (await _chat(client, sam, "What did they ask?", conversation_id=alexs)).status_code == 404

    buffer = io.BytesIO()
    Image.new("RGB", (10, 10), color="white").save(buffer, format="PNG")
    captured = (
        await client.post(
            "/api/v1/slides/analyze",
            files={"image": ("slide.png", buffer.getvalue(), "image/png")},
            data={"slide_number": "1", "lecture_title": "Lambda Calculus", "page_url": "https://example.com/a"},
            headers=alex,
        )
    ).json()
    slide_chat = await client.post(
        "/api/v1/chat",
        json={
            "conversation_id": None,
            "presentation_id": captured["presentation_id"],
            "query_mode": "slide",
            "slide_id": captured["slide_id"],
            "object_id": None,
            "message": "Explain this",
        },
        headers=alex,
    )
    assert (await _chat(client, alex, "Carry on", conversation_id=_conversation_id(slide_chat))).status_code == 404


async def test_modes_that_need_retrieval_are_still_refused(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _sign_in(db_session, "a@example.com")
    for mode in ("presentation", "auto"):
        assert (await _chat(client, headers, "x", query_mode=mode)).status_code == 400
