"""Sorting captures into series: on capture, GET /series (with backfill),
renaming, moving and deleting, and the Claude sorter's parsing.

The `client` fixture uses PlaceholderSeriesSorter, which files a capture
under its page title, so two page titles here stand for two topics."""

import io
import json
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

from httpx import AsyncClient
from conftest import FakeChatService
from PIL import Image
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_series_sorter
from app.main import app
from app.models.orm import Conversation, Note, Quiz, Series, Slide, StudyAid, UsageEvent, User
from app.models.orm import Session as SessionRow
from app.services.series_sorter import (
    ClaudeSeriesSorter,
    ExistingSeries,
    PreviousCapture,
    SlideDigest,
    SortDecision,
    _format_request,
)

API_KEY = {"X-API-Key": "test-api-key"}
LAMBDA = "Lambda Calculus"
DP = "Dynamic Programming"


def _png(color: str) -> bytes:
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


async def _capture(client: AsyncClient, headers: dict[str, str], color: str, title: str, url: str | None = None) -> dict:
    response = await client.post(
        "/api/v1/slides/analyze",
        files={"image": ("slide.png", _png(color), "image/png")},
        data={"slide_number": "1", "lecture_title": title, "page_url": url or f"https://example.com/{color}"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _series(client: AsyncClient, headers: dict[str, str]) -> dict:
    response = await client.get("/api/v1/series", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


class _FailingSorter:
    model_name = "failing"

    async def sort(self, slide: SlideDigest, existing: list[ExistingSeries], previous=None) -> SortDecision:
        raise RuntimeError("provider down")


# --- sorting on capture -------------------------------------------------------


async def test_captures_on_one_topic_share_a_series_across_pages(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _sign_in(db_session, "a@example.com")
    first = await _capture(client, headers, "white", LAMBDA, url="https://example.com/week-1")
    second = await _capture(client, headers, "black", LAMBDA, url="https://example.com/week-2")
    other = await _capture(client, headers, "red", DP)

    assert first["presentation_id"] != second["presentation_id"]  # two pages
    assert first["series"]["id"] == second["series"]["id"]  # one topic
    assert first["series"]["title"] == LAMBDA
    assert other["series"]["id"] != first["series"]["id"]

    events = (await db_session.execute(select(UsageEvent.action))).scalars().all()
    assert events.count("sort") == 3


async def test_signed_out_captures_are_not_sorted(client: AsyncClient, db_session: AsyncSession) -> None:
    captured = await _capture(client, API_KEY, "white", LAMBDA)
    assert captured["series"] is None
    assert (await db_session.execute(select(Series.id))).scalars().all() == []


async def test_a_failing_sorter_never_fails_the_capture(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _sign_in(db_session, "a@example.com")
    app.dependency_overrides[get_series_sorter] = lambda: _FailingSorter()
    captured = await _capture(client, headers, "white", LAMBDA)
    assert captured["series"] is None
    assert captured["objects"]

    body = await _series(client, headers)  # the sorter is still down
    assert body["series"] == []
    assert [c["slide_id"] for c in body["unsorted"]] == [captured["slide_id"]]


async def test_recapturing_the_same_slide_keeps_its_series(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _sign_in(db_session, "a@example.com")
    first = await _capture(client, headers, "white", LAMBDA, url="https://example.com/a")
    again = await _capture(client, headers, "white", LAMBDA, url="https://example.com/a")
    assert again["slide_id"] == first["slide_id"]
    assert again["series"] == first["series"]
    assert len((await db_session.execute(select(Series.id))).scalars().all()) == 1


# --- GET /series --------------------------------------------------------------


async def test_series_requires_sign_in(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/series", headers=API_KEY)).status_code == 401


async def test_series_lists_captures_newest_first_with_their_page(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _sign_in(db_session, "a@example.com")
    first = await _capture(client, headers, "white", LAMBDA, url="https://example.com/week-1?x=1")
    second = await _capture(client, headers, "black", LAMBDA, url="https://example.com/week-2")
    await _capture(client, headers, "red", DP)
    # SQLite timestamps tie within a second; make "first" clearly the older one.
    await db_session.execute(
        update(Slide).where(Slide.id == uuid.UUID(first["slide_id"])).values(created_at=datetime.now(UTC) - timedelta(hours=1))
    )
    await db_session.commit()

    body = await _series(client, headers)
    assert body["retention_days"] == 30
    assert body["unsorted"] == []
    by_title = {s["title"]: s for s in body["series"]}
    assert set(by_title) == {LAMBDA, DP}

    lam = by_title[LAMBDA]
    assert lam["category"] == "General"
    assert lam["cover_slide_id"] == first["slide_id"]
    assert [c["slide_id"] for c in lam["captures"]] == [second["slide_id"], first["slide_id"]]
    assert lam["captures"][1]["page_url"] == "https://example.com/week-1"
    assert lam["captures"][1]["kind"] == "lecture"


async def test_series_are_private_to_their_owner(client: AsyncClient, db_session: AsyncSession) -> None:
    alex = await _sign_in(db_session, "alex@example.com")
    sam = await _sign_in(db_session, "sam@example.com")
    captured = await _capture(client, alex, "white", LAMBDA)
    series_id = captured["series"]["id"]

    assert (await _series(client, sam))["series"] == []
    assert (await client.patch(f"/api/v1/series/{series_id}", json={"title": "Mine"}, headers=sam)).status_code == 404
    assert (await client.delete(f"/api/v1/series/{series_id}", headers=sam)).status_code == 404
    move = await client.post(f"/api/v1/slides/{captured['slide_id']}/move", json={"category": "X", "title": "Y"}, headers=sam)
    assert move.status_code == 404
    # Sam's own capture of the same topic gets Sam's own series.
    assert (await _capture(client, sam, "white", LAMBDA))["series"]["id"] != series_id


async def test_listing_sorts_captures_made_before_sorting_existed(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _sign_in(db_session, "a@example.com")
    captured = await _capture(client, headers, "white", LAMBDA)
    await db_session.execute(update(Slide).values(series_id=None, subtopic=None, content_kind=None))
    await db_session.execute(Series.__table__.delete())
    await db_session.commit()

    body = await _series(client, headers)
    assert body["unsorted"] == []
    assert [c["slide_id"] for c in body["series"][0]["captures"]] == [captured["slide_id"]]


async def test_practice_captures_are_marked(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _sign_in(db_session, "a@example.com")
    captured = await _capture(client, headers, "white", "Tutorial 3 practice questions")
    assert captured["series"]["kind"] == "practice"


# --- rename, move, delete -----------------------------------------------------


async def test_a_series_can_be_renamed_and_recategorised(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _sign_in(db_session, "a@example.com")
    captured = await _capture(client, headers, "white", LAMBDA)
    response = await client.patch(
        f"/api/v1/series/{captured['series']['id']}",
        json={"title": "  Untyped   Lambda Calculus ", "category": "Functional Programming"},
        headers=headers,
    )
    assert response.status_code == 204
    series = (await _series(client, headers))["series"][0]
    assert (series["category"], series["title"]) == ("Functional Programming", "Untyped Lambda Calculus")


async def test_the_cover_must_be_a_capture_in_the_series(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _sign_in(db_session, "a@example.com")
    first = await _capture(client, headers, "white", LAMBDA)
    second = await _capture(client, headers, "black", LAMBDA)
    other = await _capture(client, headers, "red", DP)
    url = f"/api/v1/series/{first['series']['id']}"

    assert (await client.patch(url, json={"cover_slide_id": other["slide_id"]}, headers=headers)).status_code == 422
    assert (await client.patch(url, json={"cover_slide_id": second["slide_id"]}, headers=headers)).status_code == 204
    by_title = {s["title"]: s for s in (await _series(client, headers))["series"]}
    assert by_title[LAMBDA]["cover_slide_id"] == second["slide_id"]


async def test_moving_a_capture_to_another_series(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _sign_in(db_session, "a@example.com")
    lam = await _capture(client, headers, "white", LAMBDA)
    dp = await _capture(client, headers, "red", DP)

    moved = await client.post(
        f"/api/v1/slides/{dp['slide_id']}/move", json={"series_id": lam["series"]["id"]}, headers=headers
    )
    assert moved.status_code == 200
    assert moved.json()["id"] == lam["series"]["id"]

    body = await _series(client, headers)
    assert [s["title"] for s in body["series"]] == [LAMBDA]  # the emptied series is gone
    assert len(body["series"][0]["captures"]) == 2


async def test_moving_a_capture_to_a_new_series(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _sign_in(db_session, "a@example.com")
    first = await _capture(client, headers, "white", LAMBDA)
    second = await _capture(client, headers, "black", LAMBDA)

    moved = await client.post(
        f"/api/v1/slides/{first['slide_id']}/move",
        json={"category": "Functional Programming", "title": "Church Encodings"},
        headers=headers,
    )
    assert moved.status_code == 200
    by_title = {s["title"]: s for s in (await _series(client, headers))["series"]}
    assert [c["slide_id"] for c in by_title["Church Encodings"]["captures"]] == [first["slide_id"]]
    # The old series lost its cover capture and falls back to what it still has.
    assert by_title[LAMBDA]["cover_slide_id"] == second["slide_id"]

    assert (await client.post(f"/api/v1/slides/{first['slide_id']}/move", json={}, headers=headers)).status_code == 422


async def test_deleting_a_series_removes_its_captures_and_chats(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _sign_in(db_session, "a@example.com")
    lam = await _capture(client, headers, "white", LAMBDA)
    keep = await _capture(client, headers, "red", DP)
    chat = await client.post(
        "/api/v1/chat",
        json={
            "conversation_id": None,
            "presentation_id": lam["presentation_id"],
            "query_mode": "slide",
            "slide_id": lam["slide_id"],
            "object_id": None,
            "message": "Explain this",
        },
        headers=headers,
    )
    assert chat.status_code == 200

    assert (await client.delete(f"/api/v1/series/{lam['series']['id']}", headers=headers)).status_code == 204
    assert [s["id"] for s in (await _series(client, headers))["series"]] == [keep["series"]["id"]]
    assert (await client.get(f"/api/v1/slides/{lam['slide_id']}", headers=headers)).status_code == 404
    assert (await db_session.execute(select(Conversation.id))).scalars().all() == []


async def test_deleting_the_last_capture_removes_the_series(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _sign_in(db_session, "a@example.com")
    captured = await _capture(client, headers, "white", LAMBDA)
    assert (await client.delete(f"/api/v1/slides/{captured['slide_id']}", headers=headers)).status_code == 204
    assert (await db_session.execute(select(Series.id))).scalars().all() == []


async def test_cleanup_and_account_deletion_remove_series(client: AsyncClient, db_session: AsyncSession) -> None:
    alex = await _sign_in(db_session, "alex@example.com")
    sam = await _sign_in(db_session, "sam@example.com")
    old = await _capture(client, alex, "white", LAMBDA)
    await _capture(client, alex, "red", DP)
    await _capture(client, sam, "black", DP)
    await db_session.execute(
        update(Slide).where(Slide.id == uuid.UUID(old["slide_id"])).values(created_at=datetime.now(UTC) - timedelta(days=45))
    )
    await db_session.commit()

    assert (await client.post("/api/v1/maintenance/cleanup", headers=API_KEY)).status_code == 200
    assert len((await db_session.execute(select(Series.id))).scalars().all()) == 2  # the expired one went

    assert (await client.delete("/api/v1/auth/account", headers=alex)).status_code == 204
    assert [s["title"] for s in (await _series(client, sam))["series"]] == [DP]
    assert len((await db_session.execute(select(Series.id))).scalars().all()) == 1


# --- ClaudeSeriesSorter -------------------------------------------------------

_EXISTING = [ExistingSeries("Functional Programming", "Lambda Calculus"), ExistingSeries("Algorithms", "Sorting")]
_SLIDE = SlideDigest(page_title="CSC3002 week 4", summary="Beta reduction rules.", headings=["Reduction"], text="(λx.M) N")


def _sorter(payload: dict) -> tuple[ClaudeSeriesSorter, AsyncMock]:
    fake_client = AsyncMock()
    fake_client.messages.create.return_value = SimpleNamespace(
        content=[SimpleNamespace(type="text", text=json.dumps(payload))]
    )
    return ClaudeSeriesSorter(client=fake_client, model="claude-haiku-5-5"), fake_client


async def test_sorter_picks_an_existing_series_by_number_and_keeps_its_wording() -> None:
    sorter, fake_client = _sorter(
        {"series_number": 1, "category": "FP", "title": "lambda calc", "subtopic": " Beta   Reduction ", "kind": "lecture"}
    )
    decision = await sorter.sort(_SLIDE, _EXISTING)
    assert decision == SortDecision(0, "Functional Programming", "Lambda Calculus", "Beta Reduction", "lecture")

    sent = fake_client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "1. Functional Programming | Lambda Calculus" in sent
    assert "Beta reduction rules." in sent


async def test_sorter_starts_a_new_series_when_the_number_is_null_or_out_of_range() -> None:
    for number in (None, 0, 3):
        sorter, _ = _sorter(
            {"series_number": number, "category": "Algorithms", "title": "Dynamic Programming", "subtopic": "Memoisation", "kind": "practice"}
        )
        decision = await sorter.sort(_SLIDE, _EXISTING)
        assert decision == SortDecision(None, "Algorithms", "Dynamic Programming", "Memoisation", "practice")


async def test_sorter_falls_back_when_the_model_returns_blank_names() -> None:
    sorter, _ = _sorter({"series_number": None, "category": " ", "title": "", "subtopic": "", "kind": "lecture"})
    decision = await sorter.sort(_SLIDE, [])
    assert (decision.category, decision.title) == ("General", "CSC3002 week 4")


# --- chat across the slides of a series ---------------------------------------


async def _ask(
    client: AsyncClient, headers: dict[str, str], captured: dict, conversation_id: str | None = None
) -> tuple[int, str | None]:
    response = await client.post(
        "/api/v1/chat",
        json={
            "conversation_id": conversation_id,
            "presentation_id": captured["presentation_id"],
            "query_mode": "slide",
            "slide_id": captured["slide_id"],
            "object_id": None,
            "message": "Explain this",
        },
        headers=headers,
    )
    if response.status_code != 200:
        return response.status_code, None
    return 200, response.text.split('"conversation_id": "')[1].split('"')[0]


async def test_a_chat_follows_the_student_to_the_next_slide_of_the_series(
    client: AsyncClient, db_session: AsyncSession
) -> None:

    headers = await _sign_in(db_session, "a@example.com")
    first = await _capture(client, headers, "white", LAMBDA, url="https://example.com/week-1")
    second = await _capture(client, headers, "black", LAMBDA, url="https://example.com/week-2")
    assert first["presentation_id"] != second["presentation_id"]
    # SQLite timestamps tie within a second; make "first" clearly the older one.
    await db_session.execute(
        update(Slide).where(Slide.id == uuid.UUID(first["slide_id"])).values(created_at=datetime.now(UTC) - timedelta(hours=1))
    )
    await db_session.commit()

    _, conversation_id = await _ask(client, headers, first)
    status, continued = await _ask(client, headers, second, conversation_id)
    assert (status, continued) == (200, conversation_id)

    # Reopened from Recent, the chat still knows its slide's series.
    reopened = (await client.get(f"/api/v1/conversations/{conversation_id}", headers=headers)).json()
    assert reopened["slide"]["slide_id"] == second["slide_id"]
    assert reopened["slide"]["series"] == second["series"]

    conversation = (await db_session.execute(select(Conversation))).scalar_one()
    assert str(conversation.slide_id) == second["slide_id"]
    assert str(conversation.presentation_id) == second["presentation_id"]

    # The first slide had nothing before it; the second is told about the first.
    first_prompt, second_prompt = FakeChatService.captured_system_prompts
    assert "Earlier slides" not in first_prompt
    assert f'series "{LAMBDA}" (General)' in second_prompt
    assert "Text of the slide captured just before this one" in second_prompt


async def test_a_chat_does_not_follow_to_another_series_or_another_user(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    alex = await _sign_in(db_session, "alex@example.com")
    sam = await _sign_in(db_session, "sam@example.com")
    lam = await _capture(client, alex, "white", LAMBDA)
    dp = await _capture(client, alex, "red", DP)
    sams = await _capture(client, sam, "black", LAMBDA)
    _, conversation_id = await _ask(client, alex, lam)

    assert (await _ask(client, alex, dp, conversation_id))[0] == 404  # another topic
    assert (await _ask(client, sam, sams, conversation_id))[0] == 404  # another account


async def test_chat_rejects_a_slide_from_another_presentation(client: AsyncClient, db_session: AsyncSession) -> None:
    alex = await _sign_in(db_session, "alex@example.com")
    sam = await _sign_in(db_session, "sam@example.com")
    mine = await _capture(client, sam, "white", LAMBDA)
    theirs = await _capture(client, alex, "black", DP)
    # Sam names Sam's own presentation but Alex's slide.
    status, _ = await _ask(client, sam, {"presentation_id": mine["presentation_id"], "slide_id": theirs["slide_id"]})
    assert status == 404


# --- what the sorter is told about the captures around this one -----------------


class _RecordingSorter:
    """Files everything in one series and keeps what it was shown."""

    model_name = "recording"

    def __init__(self) -> None:
        self.calls: list[tuple[list[ExistingSeries], PreviousCapture | None]] = []

    async def sort(self, slide: SlideDigest, existing: list[ExistingSeries], previous=None) -> SortDecision:
        self.calls.append((existing, previous))
        return SortDecision(
            existing_index=0 if existing else None,
            category="Functional Programming",
            title=LAMBDA,
            subtopic=f"Part {len(self.calls)}",
            kind="lecture",
        )


async def test_the_sorter_is_told_where_the_previous_capture_went(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _sign_in(db_session, "a@example.com")
    sorter = _RecordingSorter()
    app.dependency_overrides[get_series_sorter] = lambda: sorter
    first = await _capture(client, headers, "white", "Week 4", url="https://example.com/week-4")
    # Captures made in the same second would tie on SQLite's timestamps.
    await db_session.execute(
        update(Slide).where(Slide.id == uuid.UUID(first["slide_id"])).values(created_at=datetime.now(UTC) - timedelta(minutes=3, seconds=30))
    )
    await db_session.commit()
    await _capture(client, headers, "black", "Week 4", url="https://example.com/week-4")
    await _capture(client, headers, "red", "Week 5", url="https://example.com/week-5")

    assert sorter.calls[0] == ([], None)  # nothing came before the first capture
    existing, previous = sorter.calls[1]
    assert existing == [ExistingSeries("Functional Programming", LAMBDA, ("Part 1",))]
    assert previous == PreviousCapture(existing_index=0, subtopic="Part 1", minutes_ago=3, same_page=True)
    existing, previous = sorter.calls[2]
    assert set(existing[0].subtopics) == {"Part 1", "Part 2"}
    assert previous is not None and previous.same_page is False and previous.subtopic == "Part 2"


async def test_an_old_or_foreign_capture_is_not_the_previous_one(client: AsyncClient, db_session: AsyncSession) -> None:
    alex = await _sign_in(db_session, "alex@example.com")
    sam = await _sign_in(db_session, "sam@example.com")
    sorter = _RecordingSorter()
    app.dependency_overrides[get_series_sorter] = lambda: sorter
    old = await _capture(client, alex, "white", "Week 4")
    await db_session.execute(
        update(Slide).where(Slide.id == uuid.UUID(old["slide_id"])).values(created_at=datetime.now(UTC) - timedelta(hours=5))
    )
    await db_session.commit()
    await _capture(client, alex, "black", "Week 4")
    await _capture(client, sam, "red", "Week 4")

    assert sorter.calls[1][1] is None  # five hours on, the student may be on something else
    assert sorter.calls[2] == ([], None)  # another account's captures are never shown


def test_the_request_names_subtopics_and_the_previous_capture() -> None:
    existing = [ExistingSeries("Functional Programming", LAMBDA, ("Beta Reduction", "Syntax")), ExistingSeries("Algorithms", "Sorting")]
    text = _format_request(_SLIDE, existing, PreviousCapture(existing_index=0, subtopic="Beta Reduction", minutes_ago=2, same_page=True))
    assert "1. Functional Programming | Lambda Calculus (so far: Beta Reduction; Syntax)" in text
    assert "2. Algorithms | Sorting" in text and "Sorting (so far" not in text
    assert 'Captured 2 min ago from the same page as this slide, about "Beta Reduction". It was filed in series 1.' in text
    assert "<previous_capture>" not in _format_request(_SLIDE, existing)


# --- a series named after its first slide can be given a wider title -----------------


async def test_sorter_passes_on_a_wider_title_only_when_it_differs() -> None:
    base = {"series_number": 1, "category": "FP", "title": "Lambda Calculus", "subtopic": "Lazy Evaluation", "kind": "lecture"}
    sorter, _ = _sorter({**base, "broader_title": "  Functional   Programming "})
    assert (await sorter.sort(_SLIDE, _EXISTING)).retitle == "Functional Programming"
    for unchanged in ("", "lambda calculus"):
        sorter, _ = _sorter({**base, "broader_title": unchanged})
        assert (await sorter.sort(_SLIDE, _EXISTING)).retitle is None
    # A new series is named by its title; there is nothing to widen.
    sorter, _ = _sorter({**base, "series_number": None, "broader_title": "Anything"})
    assert (await sorter.sort(_SLIDE, _EXISTING)).retitle is None


class _WideningSorter:
    """Starts a narrowly named series, then asks for a wider title on every later slide."""

    model_name = "widening"

    def __init__(self, wider: str) -> None:
        self.wider = wider

    async def sort(self, slide: SlideDigest, existing: list[ExistingSeries], previous=None) -> SortDecision:
        index = next((i for i, series in enumerate(existing) if series.category == "Algorithms"), None)
        return SortDecision(
            existing_index=index,
            category="Algorithms",
            title="Big-O Notation",
            subtopic="Hash Tables",
            kind="lecture",
            retitle=self.wider if index is not None else None,
        )


async def test_a_new_series_takes_a_wider_title_but_an_older_one_keeps_its_name(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    headers = await _sign_in(db_session, "a@example.com")
    app.dependency_overrides[get_series_sorter] = lambda: _WideningSorter("Data Structures")
    first = await _capture(client, headers, "white", "DSA course")
    assert first["series"]["title"] == "Big-O Notation"
    second = await _capture(client, headers, "black", "DSA course")
    assert second["series"] == {**first["series"], "title": "Data Structures", "subtopic": "Hash Tables"}

    # A day later the name is the student's: the sorter no longer changes it.
    await db_session.execute(update(Series).values(created_at=datetime.now(UTC) - timedelta(days=1)))
    await db_session.commit()
    app.dependency_overrides[get_series_sorter] = lambda: _WideningSorter("Computer Science")
    third = await _capture(client, headers, "red", "DSA course")
    assert third["series"]["title"] == "Data Structures"


async def test_a_wider_title_never_duplicates_another_series(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _sign_in(db_session, "a@example.com")
    user_id = (await db_session.execute(select(User.id))).scalar_one()
    db_session.add(Series(user_id=user_id, category="algorithms", title="data structures"))
    await db_session.commit()
    app.dependency_overrides[get_series_sorter] = lambda: _WideningSorter("Data Structures")
    await _capture(client, headers, "white", "DSA course")
    second = await _capture(client, headers, "black", "DSA course")
    assert second["series"]["title"] == "Big-O Notation"


# --- sorting existing captures again ---------------------------------------------


class _OneLectureSorter:
    """Keeps a capture with the one before it, as the real sorter does for one lecture."""

    model_name = "one-lecture"

    async def sort(self, slide: SlideDigest, existing: list[ExistingSeries], previous=None) -> SortDecision:
        return SortDecision(
            existing_index=previous.existing_index if previous is not None else None,
            category="Algorithms",
            title="Data Structures",
            subtopic=slide.page_title,
            kind="lecture",
        )


async def _spread_out(db_session: AsyncSession, captures: list[dict]) -> None:
    """Captures made in the same second would tie on SQLite's timestamps."""
    for position, capture in enumerate(captures):
        await db_session.execute(
            update(Slide)
            .where(Slide.id == uuid.UUID(capture["slide_id"]))
            .values(created_at=datetime.now(UTC) - timedelta(minutes=30 - 2 * position))
        )
    await db_session.commit()


async def _resort(client: AsyncClient, headers: dict[str, str]) -> list[dict]:
    """Runs the pass the way the panel does: again from `processed` until done."""
    steps, offset = [], 0
    while True:
        response = await client.post("/api/v1/series/resort", json={"offset": offset}, headers=headers)
        assert response.status_code == 200, response.text
        steps.append(response.json())
        if steps[-1]["done"]:
            return steps
        offset = steps[-1]["processed"]


async def test_sorting_again_brings_a_split_lecture_together(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _sign_in(db_session, "a@example.com")
    # The placeholder sorter makes a series per page title: one lecture, split in three.
    titles = ["Big-O Notation", "Hash Tables", "Heaps"]
    captures = [await _capture(client, headers, color, title) for color, title in zip(["white", "black", "red"], titles)]
    await _spread_out(db_session, captures)
    assert len({c["series"]["id"] for c in captures}) == 3

    user_id = (await db_session.execute(select(User.id))).scalar_one()
    last = uuid.UUID(captures[2]["series"]["id"])
    db_session.add_all(
        [
            Note(user_id=user_id, series_id=last, slide_id=None, topic="Heaps", title="My note", body="x", source="user"),
            Quiz(user_id=user_id, series_id=last, title="Heaps quiz", questions=[], resources=[]),
            StudyAid(user_id=user_id, series_id=last, kind="guide", title="Heaps guide", content={"markdown": "x"}, progress=[]),
        ]
    )
    await db_session.commit()

    app.dependency_overrides[get_series_sorter] = lambda: _OneLectureSorter()
    steps = await _resort(client, headers)
    assert steps == [{"processed": 3, "total": 3, "done": True}]

    body = await _series(client, headers)
    assert [s["title"] for s in body["series"]] == ["Data Structures"]
    assert [c["subtopic"] for c in body["series"][0]["captures"]][::-1] == titles
    assert body["unsorted"] == []
    # The emptied series are gone, and what was made for them moved along.
    kept = uuid.UUID(body["series"][0]["id"])
    assert (await db_session.execute(select(Series.id))).scalars().all() == [kept]
    for model in (Note, Quiz, StudyAid):
        assert (await db_session.execute(select(model.series_id))).scalars().all() == [kept]


async def test_sorting_again_goes_a_few_captures_at_a_time(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _sign_in(db_session, "a@example.com")
    colors = ["white", "black", "red", "blue", "green", "yellow", "orange", "purple"]
    captures = [await _capture(client, headers, color, f"Slide {n}") for n, color in enumerate(colors)]
    await _spread_out(db_session, captures)

    app.dependency_overrides[get_series_sorter] = lambda: _OneLectureSorter()
    steps = await _resort(client, headers)
    assert steps == [{"processed": 6, "total": 8, "done": False}, {"processed": 8, "total": 8, "done": True}]
    assert len((await _series(client, headers))["series"]) == 1


async def test_sorting_again_is_per_account_and_survives_a_failing_sorter(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    alex = await _sign_in(db_session, "alex@example.com")
    sam = await _sign_in(db_session, "sam@example.com")
    mine = [await _capture(client, alex, "white", "Big-O Notation"), await _capture(client, alex, "black", "Heaps")]
    theirs = await _capture(client, sam, "red", "Friction")
    await _spread_out(db_session, mine)

    assert (await client.post("/api/v1/series/resort", json={}, headers=API_KEY)).status_code == 401

    app.dependency_overrides[get_series_sorter] = lambda: _FailingSorter()
    assert (await _resort(client, alex))[-1]["done"] is True
    assert len((await _series(client, alex))["series"]) == 2  # nothing moved, nothing lost

    app.dependency_overrides[get_series_sorter] = lambda: _OneLectureSorter()
    await _resort(client, alex)
    assert len((await _series(client, alex))["series"]) == 1
    assert [s["id"] for s in (await _series(client, sam))["series"]] == [theirs["series"]["id"]]
