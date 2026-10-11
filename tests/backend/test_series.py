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
from PIL import Image
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_series_sorter
from app.main import app
from app.models.orm import Conversation, Series, Slide, UsageEvent, User
from app.models.orm import Session as SessionRow
from app.services.series_sorter import ClaudeSeriesSorter, ExistingSeries, SlideDigest, SortDecision

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

    async def sort(self, slide: SlideDigest, existing: list[ExistingSeries]) -> SortDecision:
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
