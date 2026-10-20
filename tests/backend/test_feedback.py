"""👍/👎 on answers: who may rate what, that a second rating replaces the
first, signed-out ratings, the daily cap, the admin list, and that feedback
goes with the account."""

import io
import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.orm import Feedback, User
from app.models.orm import Session as SessionRow

API_KEY = {"X-API-Key": "test-api-key"}
ADMIN_EMAIL = "owner@example.com"


@pytest.fixture(autouse=True)
def admin_and_cap(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "admin_emails", ADMIN_EMAIL)
    monkeypatch.setattr(settings, "rate_limit_feedback_per_day", 60)


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


async def _capture(client: AsyncClient, headers: dict[str, str], colour: str = "white") -> dict:
    buffer = io.BytesIO()
    Image.new("RGB", (10, 10), color=colour).save(buffer, format="PNG")
    response = await client.post(
        "/api/v1/slides/analyze",
        files={"image": ("slide.png", buffer.getvalue(), "image/png")},
        data={"slide_number": "1", "lecture_title": "Lambda Calculus", "page_url": "https://example.com/a"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _chat_reply_id(client: AsyncClient, headers: dict[str, str], captured: dict) -> str:
    response = await client.post(
        "/api/v1/chat",
        json={
            "presentation_id": captured["presentation_id"],
            "query_mode": "slide",
            "slide_id": captured["slide_id"],
            "message": "Summarize this slide.",
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    for block in response.text.strip().split("\n\n"):
        lines = block.strip().splitlines()
        if "event: done" in lines:
            return json.loads(next(line.removeprefix("data: ") for line in lines if line.startswith("data: ")))[
                "message_id"
            ]
    raise AssertionError("no done event")


async def _rate(client: AsyncClient, headers: dict[str, str], **body) -> "object":
    return await client.post("/api/v1/feedback", json=body, headers=headers)


async def _all_feedback(db_session: AsyncSession) -> list[Feedback]:
    db_session.expire_all()
    return list((await db_session.execute(select(Feedback))).scalars())


async def test_a_summary_rating_keeps_the_rated_text(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _sign_in(db_session, "a@example.com")
    captured = await _capture(client, headers)

    response = await _rate(client, headers, target="summary", slide_id=captured["slide_id"], rating="up")

    assert response.status_code == 200, response.text
    assert response.json()["rating"] == "up"
    [feedback] = await _all_feedback(db_session)
    assert feedback.rating == "up"
    assert feedback.slide_id == uuid.UUID(captured["slide_id"])
    assert feedback.answer_excerpt == captured["summary"]


async def test_a_chat_reply_can_be_rated_down_with_a_comment(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _sign_in(db_session, "a@example.com")
    captured = await _capture(client, headers)
    message_id = await _chat_reply_id(client, headers, captured)

    response = await _rate(
        client, headers, target="chat", message_id=message_id, rating="down", comment="  Misread the equation  "
    )

    assert response.status_code == 200, response.text
    [feedback] = await _all_feedback(db_session)
    assert (feedback.target, feedback.rating, feedback.comment) == ("chat", "down", "Misread the equation")
    assert feedback.answer_excerpt == "Fake answer."


async def test_rating_again_changes_the_first_rating(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _sign_in(db_session, "a@example.com")
    captured = await _capture(client, headers)

    await _rate(client, headers, target="summary", slide_id=captured["slide_id"], rating="up")
    await _rate(client, headers, target="summary", slide_id=captured["slide_id"], rating="down", comment="Wrong")

    [feedback] = await _all_feedback(db_session)
    assert (feedback.rating, feedback.comment) == ("down", "Wrong")


async def test_another_students_answers_cannot_be_rated(client: AsyncClient, db_session: AsyncSession) -> None:
    owner = await _sign_in(db_session, "a@example.com")
    other = await _sign_in(db_session, "b@example.com")
    captured = await _capture(client, owner)
    message_id = await _chat_reply_id(client, owner, captured)

    for headers in (other, API_KEY):
        summary = await _rate(client, headers, target="summary", slide_id=captured["slide_id"], rating="down")
        reply = await _rate(client, headers, target="chat", message_id=message_id, rating="down")
        assert (summary.status_code, reply.status_code) == (404, 404)
    assert await _all_feedback(db_session) == []


async def test_unknown_answers_and_long_comments_are_refused(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _sign_in(db_session, "a@example.com")
    captured = await _capture(client, headers)

    assert (await _rate(client, headers, target="summary", slide_id=str(uuid.uuid4()), rating="up")).status_code == 404
    assert (await _rate(client, headers, target="summary", slide_id="not-an-id", rating="up")).status_code == 404
    assert (await _rate(client, headers, target="chat", rating="up")).status_code == 404
    too_long = await _rate(
        client, headers, target="summary", slide_id=captured["slide_id"], rating="down", comment="x" * 1001
    )
    assert too_long.status_code == 422


async def test_a_signed_out_student_can_rate_their_own_capture(client: AsyncClient, db_session: AsyncSession) -> None:
    captured = await _capture(client, API_KEY)

    first = await _rate(client, API_KEY, target="summary", slide_id=captured["slide_id"], rating="up")
    assert first.status_code == 200, first.text
    # The id it came back with lets the same student change their mind.
    await _rate(
        client, API_KEY, target="summary", slide_id=captured["slide_id"], rating="down", feedback_id=first.json()["id"]
    )

    [feedback] = await _all_feedback(db_session)
    assert feedback.user_id is None
    assert feedback.rating == "down"


async def test_feedback_has_a_daily_cap(client: AsyncClient, db_session: AsyncSession, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "rate_limit_feedback_per_day", 2)
    captured = await _capture(client, API_KEY)

    statuses = [
        (await _rate(client, API_KEY, target="summary", slide_id=captured["slide_id"], rating="up")).status_code
        for _ in range(3)
    ]

    assert statuses == [200, 200, 429]


async def test_admin_sees_thumbs_down_first(client: AsyncClient, db_session: AsyncSession) -> None:
    student = await _sign_in(db_session, "a@example.com")
    admin = await _sign_in(db_session, ADMIN_EMAIL)
    liked = await _capture(client, student, colour="white")
    disliked = await _capture(client, student, colour="black")
    anonymous = await _capture(client, API_KEY, colour="red")
    await _rate(client, student, target="summary", slide_id=liked["slide_id"], rating="up")
    await _rate(client, student, target="summary", slide_id=disliked["slide_id"], rating="down", comment="Off topic")
    await _rate(client, API_KEY, target="summary", slide_id=anonymous["slide_id"], rating="down")

    assert (await client.get("/api/v1/admin/feedback", headers=student)).status_code == 403
    response = await client.get("/api/v1/admin/feedback", headers=admin)

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["up"], body["down"], body["down_with_comment"]) == (1, 2, 1)
    assert (body["signed_in"], body["signed_out"]) == (2, 1)
    assert [entry["rating"] for entry in body["entries"]] == ["down", "down", "up"]
    assert {entry["email"] for entry in body["entries"][:2]} == {"a@example.com", None}


async def test_feedback_goes_with_the_account(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _sign_in(db_session, "a@example.com")
    captured = await _capture(client, headers)
    await _rate(client, headers, target="summary", slide_id=captured["slide_id"], rating="down", comment="Wrong")

    assert (await client.delete("/api/v1/auth/account", headers=headers)).status_code == 204

    assert await _all_feedback(db_session) == []
