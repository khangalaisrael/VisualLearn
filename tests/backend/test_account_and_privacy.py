"""Account deletion (DELETE /auth/account) and the public privacy page."""

import io
import uuid
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.orm import Conversation, Message, ObjectRecord, Presentation, RateLimitEvent, Slide, User
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


async def _capture_and_chat(client: AsyncClient, headers: dict[str, str]) -> None:
    buffer = io.BytesIO()
    Image.new("RGB", (10, 10), color="white").save(buffer, format="PNG")
    captured = (
        await client.post(
            "/api/v1/slides/analyze",
            files={"image": ("slide.png", buffer.getvalue(), "image/png")},
            data={"slide_number": "1"},
            headers=headers,
        )
    ).json()
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


async def _count(db_session: AsyncSession, model) -> int:
    return (await db_session.execute(select(func.count()).select_from(model))).scalar_one()


async def test_delete_account_requires_sign_in(client: AsyncClient) -> None:
    assert (await client.delete("/api/v1/auth/account", headers=API_KEY)).status_code == 401


async def test_delete_account_removes_everything_of_that_user_only(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    leaving = await _sign_in(db_session, "leaving@example.com")
    staying = await _sign_in(db_session, "staying@example.com")
    await _capture_and_chat(client, leaving)
    await _capture_and_chat(client, staying)
    db_session.add(RateLimitEvent(key=f"user:{uuid.uuid4()}", action="chat"))
    await db_session.commit()
    before = {m: await _count(db_session, m) for m in (Conversation, Message, Presentation, Slide, ObjectRecord)}

    response = await client.delete("/api/v1/auth/account", headers=leaving)
    assert response.status_code == 204

    # Exactly one user's worth of rows is gone, and the other user's chat remains.
    for model, count in before.items():
        assert await _count(db_session, model) == count // 2, model.__name__
    remaining_users = (await db_session.execute(select(User.email))).scalars().all()
    assert remaining_users == ["staying@example.com"]
    assert (await client.get("/api/v1/conversations", headers=staying)).json()["conversations"] != []
    # The deleted user's session no longer authenticates.
    assert (await client.get("/api/v1/conversations", headers=leaving)).status_code == 401


async def test_privacy_page_is_public_and_states_the_real_retention(client: AsyncClient) -> None:
    response = await client.get("/privacy")  # no API key
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert f"{get_settings().chat_retention_days} days" in response.text
    assert "Anthropic" in response.text
    assert "do not store the image" in response.text


async def test_privacy_page_shows_the_configured_contact_email_escaped(client: AsyncClient) -> None:
    settings = get_settings()
    original = settings.privacy_contact_email
    settings.privacy_contact_email = 'help@example.com"><script>x</script>'
    try:
        text = (await client.get("/privacy")).text
    finally:
        settings.privacy_contact_email = original
    assert "<script>x</script>" not in text
    assert "help@example.com" in text
