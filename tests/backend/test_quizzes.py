"""Quizzes: generating from a series, listing, attempts, the daily allowance,
ownership, tutor-mode chat on a question, cleanup, and the generator's parsing.

The `client` fixture uses PlaceholderQuizGenerator (question i is correct at
option i % 4, drawn from slide i % number-of-slides)."""

import io
import json
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from conftest import FakeChatService
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.orm import Quiz, QuizAttempt, UsageEvent, User
from app.models.orm import Session as SessionRow
from app.services.quiz_generator import ClaudeQuizGenerator, QuizSource, format_source, parse_quiz

API_KEY = {"X-API-Key": "test-api-key"}
LAMBDA = "Lambda Calculus"


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


async def _capture(client: AsyncClient, headers: dict[str, str], color: str = "white", title: str = LAMBDA) -> dict:
    buffer = io.BytesIO()
    Image.new("RGB", (10, 10), color=color).save(buffer, format="PNG")
    response = await client.post(
        "/api/v1/slides/analyze",
        files={"image": ("slide.png", buffer.getvalue(), "image/png")},
        data={"slide_number": "1", "lecture_title": title, "page_url": f"https://example.com/{color}"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _quiz(client: AsyncClient, headers: dict[str, str], series_id: str, **body) -> dict:
    response = await client.post(f"/api/v1/series/{series_id}/quizzes", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def quiz_limit():
    settings = get_settings()
    original = (settings.rate_limit_quizzes_per_day, settings.admin_emails)
    settings.admin_emails = ""
    yield settings
    settings.rate_limit_quizzes_per_day, settings.admin_emails = original


# --- generating ---------------------------------------------------------------


async def test_a_quiz_is_written_from_the_series_slides(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _sign_in(db_session, "a@example.com")
    first = await _capture(client, headers, "white")
    second = await _capture(client, headers, "black")
    quiz = await _quiz(client, headers, first["series"]["id"], count=4)

    assert quiz["title"] == "Lambda Calculus quiz"
    assert (quiz["question_count"], quiz["attempts"], quiz["best_score"]) == (4, 0, None)
    assert [q["correct_index"] for q in quiz["questions"]] == [0, 1, 2, 3]
    assert all(len(q["options"]) == 4 for q in quiz["questions"])
    assert {q["slide_id"] for q in quiz["questions"]} == {first["slide_id"], second["slide_id"]}
    assert quiz["resources"] == []
    assert "quiz" in (await db_session.execute(select(UsageEvent.action))).scalars().all()

    again = await client.get(f"/api/v1/quizzes/{quiz['id']}", headers=headers)
    assert again.json()["questions"] == quiz["questions"]


async def test_quiz_requests_are_validated(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _sign_in(db_session, "a@example.com")
    captured = await _capture(client, headers)
    url = f"/api/v1/series/{captured['series']['id']}/quizzes"
    assert (await client.post(url, json={"count": 2}, headers=headers)).status_code == 422
    assert (await client.post(url, json={"count": 11}, headers=headers)).status_code == 422
    assert (await client.post(url, json={}, headers=API_KEY)).status_code == 401
    # Web research is not open to non-admins.
    assert (await client.post(url, json={"research": True}, headers=headers)).status_code == 403


async def test_quizzes_are_private_to_their_owner(client: AsyncClient, db_session: AsyncSession) -> None:
    alex = await _sign_in(db_session, "alex@example.com")
    sam = await _sign_in(db_session, "sam@example.com")
    captured = await _capture(client, alex)
    series_id = captured["series"]["id"]
    quiz = await _quiz(client, alex, series_id)

    assert (await client.post(f"/api/v1/series/{series_id}/quizzes", json={}, headers=sam)).status_code == 404
    assert (await client.get(f"/api/v1/series/{series_id}/quizzes", headers=sam)).status_code == 404
    assert (await client.get(f"/api/v1/quizzes/{quiz['id']}", headers=sam)).status_code == 404
    assert (await client.post(f"/api/v1/quizzes/{quiz['id']}/attempts", json={"answers": [0] * 5}, headers=sam)).status_code == 404
    assert (await client.delete(f"/api/v1/quizzes/{quiz['id']}", headers=sam)).status_code == 404


async def test_the_daily_quiz_allowance(client: AsyncClient, db_session: AsyncSession, quiz_limit) -> None:
    quiz_limit.rate_limit_quizzes_per_day = 2
    headers = await _sign_in(db_session, "a@example.com")
    series_id = (await _capture(client, headers))["series"]["id"]
    await _quiz(client, headers, series_id)
    await _quiz(client, headers, series_id)
    refused = await client.post(f"/api/v1/series/{series_id}/quizzes", json={}, headers=headers)
    assert refused.status_code == 429
    assert "new quizzes" in refused.json()["detail"]
    assert refused.headers["X-Limit-Kind"] == "daily"


# --- taking -------------------------------------------------------------------


async def test_attempts_are_marked_and_the_best_score_is_listed(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _sign_in(db_session, "a@example.com")
    series_id = (await _capture(client, headers))["series"]["id"]
    quiz = await _quiz(client, headers, series_id, count=4)
    url = f"/api/v1/quizzes/{quiz['id']}/attempts"

    assert (await client.post(url, json={"answers": [0, 1]}, headers=headers)).status_code == 422
    first = await client.post(url, json={"answers": [0, 0, None, 0]}, headers=headers)  # only the first is right
    assert first.json() == {"score": 1, "total": 4}
    second = await client.post(url, json={"answers": [0, 1, 2, 0]}, headers=headers)
    assert second.json() == {"score": 3, "total": 4}

    listed = (await client.get(f"/api/v1/series/{series_id}/quizzes", headers=headers)).json()["quizzes"]
    assert [(q["id"], q["attempts"], q["best_score"]) for q in listed] == [(quiz["id"], 2, 3)]


async def test_deleting_a_quiz_a_series_or_an_account_removes_attempts(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    headers = await _sign_in(db_session, "a@example.com")
    lam = await _capture(client, headers, "white", LAMBDA)
    dp = await _capture(client, headers, "red", "Dynamic Programming")
    one = await _quiz(client, headers, lam["series"]["id"], count=3)
    two = await _quiz(client, headers, lam["series"]["id"], count=3)
    three = await _quiz(client, headers, dp["series"]["id"], count=3)
    for quiz in (one, two, three):
        await client.post(f"/api/v1/quizzes/{quiz['id']}/attempts", json={"answers": [0, 0, 0]}, headers=headers)

    assert (await client.delete(f"/api/v1/quizzes/{one['id']}", headers=headers)).status_code == 204
    assert len((await db_session.execute(select(QuizAttempt.id))).scalars().all()) == 2

    assert (await client.delete(f"/api/v1/series/{lam['series']['id']}", headers=headers)).status_code == 204
    assert [str(q) for q in (await db_session.execute(select(Quiz.id))).scalars().all()] == [three["id"]]

    assert (await client.delete("/api/v1/auth/account", headers=headers)).status_code == 204
    assert (await db_session.execute(select(Quiz.id))).scalars().all() == []
    assert (await db_session.execute(select(QuizAttempt.id))).scalars().all() == []


async def test_cleanup_expires_old_quizzes(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _sign_in(db_session, "a@example.com")
    series_id = (await _capture(client, headers))["series"]["id"]
    old = await _quiz(client, headers, series_id, count=3)
    fresh = await _quiz(client, headers, series_id, count=3)
    await client.post(f"/api/v1/quizzes/{old['id']}/attempts", json={"answers": [0, 0, 0]}, headers=headers)
    await db_session.execute(
        update(Quiz).where(Quiz.id == uuid.UUID(old["id"])).values(created_at=datetime.now(UTC) - timedelta(days=45))
    )
    await db_session.commit()

    assert (await client.post("/api/v1/maintenance/cleanup", headers=API_KEY)).status_code == 200
    assert [str(q) for q in (await db_session.execute(select(Quiz.id))).scalars().all()] == [fresh["id"]]
    assert (await db_session.execute(select(QuizAttempt.id))).scalars().all() == []


# --- tutor mode ---------------------------------------------------------------


async def _tutor(client: AsyncClient, headers: dict[str, str], **fields):
    return await client.post(
        "/api/v1/chat",
        json={
            "conversation_id": None,
            "presentation_id": None,
            "query_mode": "tutor",
            "slide_id": None,
            "object_id": None,
            "message": "Why is my answer wrong?",
            **fields,
        },
        headers=headers,
    )


async def test_tutor_chat_is_grounded_on_the_question_and_the_students_choice(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    headers = await _sign_in(db_session, "a@example.com")
    captured = await _capture(client, headers)
    quiz = await _quiz(client, headers, captured["series"]["id"], count=3)

    response = await _tutor(client, headers, quiz_id=quiz["id"], question_index=1, selected_index=3)
    assert response.status_code == 200, response.text
    prompt = FakeChatService.captured_system_prompts[-1]
    assert "Placeholder question 2 about Lambda Calculus?" in prompt
    assert "The student chose: D. Fourth option (incorrect)" in prompt
    assert "Correct option: B. Second option" in prompt
    assert "Slide the question was drawn from" in prompt
    assert prompt.startswith("You are VisionLearn, a STEM tutor. The student has just answered")

    # A follow-up continues the same conversation.
    conversation_id = response.text.split('"conversation_id": "')[1].split('"')[0]
    follow_up = await _tutor(
        client, headers, quiz_id=quiz["id"], question_index=1, selected_index=3, conversation_id=conversation_id
    )
    assert conversation_id in follow_up.text


async def test_tutor_chat_rejects_other_peoples_quizzes_and_bad_indexes(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    alex = await _sign_in(db_session, "alex@example.com")
    sam = await _sign_in(db_session, "sam@example.com")
    quiz = await _quiz(client, alex, (await _capture(client, alex))["series"]["id"], count=3)

    assert (await _tutor(client, sam, quiz_id=quiz["id"], question_index=0, selected_index=0)).status_code == 404
    assert (await _tutor(client, API_KEY, quiz_id=quiz["id"], question_index=0, selected_index=0)).status_code == 404
    assert (await _tutor(client, alex, quiz_id=quiz["id"], question_index=3, selected_index=0)).status_code == 400
    assert (await _tutor(client, alex, quiz_id=quiz["id"], question_index=0, selected_index=4)).status_code == 400
    assert (await _tutor(client, alex, question_index=0)).status_code == 400


async def test_tutor_chat_still_works_after_the_slide_is_deleted(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _sign_in(db_session, "a@example.com")
    first = await _capture(client, headers, "white")
    await _capture(client, headers, "black")
    quiz = await _quiz(client, headers, first["series"]["id"], count=3)
    question = next(i for i, q in enumerate(quiz["questions"]) if q["slide_id"] == first["slide_id"])
    assert (await client.delete(f"/api/v1/slides/{first['slide_id']}", headers=headers)).status_code == 204

    response = await _tutor(client, headers, quiz_id=quiz["id"], question_index=question, selected_index=None)
    assert response.status_code == 200
    prompt = FakeChatService.captured_system_prompts[-1]
    assert "The student skipped this question." in prompt
    assert "Slide the question was drawn from" not in prompt


# --- ClaudeQuizGenerator --------------------------------------------------------

_SOURCE = QuizSource(category="Functional Programming", title=LAMBDA, slides=["syntax", "beta reduction"], practice=["Q1. Reduce..."])


def _question(**overrides) -> dict:
    return {
        "question": "What does $(\\lambda x. x)\\, a$ reduce to?",
        "options": ["$a$", "$x$", "$\\lambda x. a$", "It has no normal form"],
        "correct_index": 0,
        "explanation": "Substitute $a$ for $x$.",
        "source_slide": 2,
        **overrides,
    }


def test_the_request_numbers_slides_and_includes_practice_questions() -> None:
    text = format_source(_SOURCE, 5)
    assert "[Slide 1]\nsyntax" in text and "[Slide 2]\nbeta reduction" in text
    assert "<practice_questions_from_the_course>\nQ1. Reduce..." in text
    assert text.endswith("Write 5 questions.")
    assert "practice_questions" not in format_source(QuizSource("C", "T", ["s"]), 3)


def test_malformed_questions_are_dropped_and_slides_mapped() -> None:
    payload = {
        "title": "  Beta   reduction basics ",
        "questions": [
            _question(),
            _question(options=["a", "b", "c"]),  # three options
            _question(correct_index=4),  # no such option
            _question(source_slide=9),  # no such slide: kept, without a slide
        ],
    }
    quiz = parse_quiz(payload, _SOURCE, 5)
    assert quiz.title == "Beta reduction basics"
    assert [q.source_index for q in quiz.questions] == [1, None]

    with pytest.raises(ValueError):
        parse_quiz({"title": "x", "questions": [_question(options=[])]}, _SOURCE, 5)


async def test_generator_calls_the_model_once_and_trims_to_the_requested_count() -> None:
    fake_client = AsyncMock()
    fake_client.messages.create.return_value = SimpleNamespace(
        content=[SimpleNamespace(type="text", text=json.dumps({"title": "T", "questions": [_question()] * 4}))]
    )
    generator = ClaudeQuizGenerator(client=fake_client, model="claude-haiku-5-5")
    quiz = await generator.generate(_SOURCE, 3)
    assert len(quiz.questions) == 3
    assert fake_client.messages.create.call_count == 1
    assert fake_client.messages.create.call_args.kwargs["model"] == "claude-haiku-5-5"
