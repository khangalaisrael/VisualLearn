"""Study aids: writing a guide, a cheat sheet and flashcards for a series,
replacing on remake, flashcard progress, the daily allowance, ownership,
cleanup, and the generator's parsing.

The `client` fixture uses PlaceholderStudyAidGenerator (8 cards for a
one-slide series)."""

import io
import json
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from conftest import streaming_client
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_study_aid_generator
from app.core.config import get_settings
from app.main import app
from app.models.orm import Slide, StudyAid, UsageEvent, User
from app.models.orm import Session as SessionRow
from app.services.series_source import SeriesText
from app.services.study_aid_generator import (
    MAX_CARDS,
    Card,
    ClaudeStudyAidGenerator,
    GeneratedAid,
    card_count,
    parse_cards,
)

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


async def _series(client: AsyncClient, headers: dict[str, str], color: str = "white", title: str = LAMBDA) -> str:
    buffer = io.BytesIO()
    Image.new("RGB", (10, 10), color=color).save(buffer, format="PNG")
    response = await client.post(
        "/api/v1/slides/analyze",
        files={"image": ("slide.png", buffer.getvalue(), "image/png")},
        data={"slide_number": "1", "lecture_title": title, "page_url": f"https://example.com/{color}"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()["series"]["id"]


async def _make(client: AsyncClient, headers: dict[str, str], series_id: str, kind: str) -> dict:
    response = await client.post(f"/api/v1/series/{series_id}/study-aids", json={"kind": kind}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def _listed(client: AsyncClient, headers: dict[str, str], series_id: str) -> list[dict]:
    response = await client.get(f"/api/v1/series/{series_id}/study-aids", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["aids"]


@pytest.fixture
def aid_limit():
    settings = get_settings()
    original = (settings.rate_limit_study_aids_per_day, settings.admin_emails)
    settings.admin_emails = ""
    yield settings
    settings.rate_limit_study_aids_per_day, settings.admin_emails = original


# --- writing -------------------------------------------------------------------


async def test_each_kind_can_be_written_for_a_series(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _sign_in(db_session, "a@example.com")
    series_id = await _series(client, headers)

    guide = await _make(client, headers, series_id, "guide")
    assert (guide["kind"], guide["title"]) == ("guide", "Lambda Calculus study guide")
    assert guide["markdown"].startswith("## Placeholder study guide")
    assert (guide["cards"], guide["card_count"], guide["known_count"]) == (None, None, None)

    sheet = await _make(client, headers, series_id, "cheatsheet")
    assert sheet["title"] == "Lambda Calculus cheat sheet" and "cheat sheet" in sheet["markdown"]

    deck = await _make(client, headers, series_id, "flashcards")
    assert deck["markdown"] is None
    assert (deck["card_count"], deck["known_count"], deck["known"]) == (8, 0, [])
    assert deck["cards"][0] == {"front": "Placeholder question 1?", "back": "Placeholder answer 1."}

    assert {aid["kind"] for aid in await _listed(client, headers, series_id)} == {"guide", "cheatsheet", "flashcards"}
    assert (await client.get(f"/api/v1/study-aids/{deck['id']}", headers=headers)).json() == deck
    events = (await db_session.execute(select(UsageEvent.action))).scalars().all()
    assert events.count("study_aid") == 3


async def test_writing_again_replaces_the_earlier_one_of_that_kind(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _sign_in(db_session, "a@example.com")
    series_id = await _series(client, headers)
    first = await _make(client, headers, series_id, "flashcards")
    await client.patch(f"/api/v1/study-aids/{first['id']}/progress", json={"known": [0, 1]}, headers=headers)
    guide = await _make(client, headers, series_id, "guide")

    second = await _make(client, headers, series_id, "flashcards")
    assert second["id"] != first["id"] and second["known"] == []
    assert (await client.get(f"/api/v1/study-aids/{first['id']}", headers=headers)).status_code == 404
    assert {aid["id"] for aid in await _listed(client, headers, series_id)} == {second["id"], guide["id"]}


async def test_a_failed_remake_keeps_the_existing_one(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _sign_in(db_session, "a@example.com")
    series_id = await _series(client, headers)
    kept = await _make(client, headers, series_id, "guide")

    class _Failing:
        model_name = "failing"

        async def generate(self, kind, source) -> GeneratedAid:
            raise RuntimeError("provider down")

    app.dependency_overrides[get_study_aid_generator] = lambda: _Failing()
    failed = await client.post(f"/api/v1/series/{series_id}/study-aids", json={"kind": "guide"}, headers=headers)
    assert failed.status_code == 502
    assert [aid["id"] for aid in await _listed(client, headers, series_id)] == [kept["id"]]


async def test_requests_are_validated_and_private(client: AsyncClient, db_session: AsyncSession) -> None:
    alex = await _sign_in(db_session, "alex@example.com")
    sam = await _sign_in(db_session, "sam@example.com")
    series_id = await _series(client, alex)
    url = f"/api/v1/series/{series_id}/study-aids"
    deck = await _make(client, alex, series_id, "flashcards")

    assert (await client.post(url, json={"kind": "mindmap"}, headers=alex)).status_code == 422
    assert (await client.post(url, json={"kind": "guide"}, headers=API_KEY)).status_code == 401
    assert (await client.post(url, json={"kind": "guide"}, headers=sam)).status_code == 404
    assert (await client.get(url, headers=sam)).status_code == 404
    assert (await client.get(f"/api/v1/study-aids/{deck['id']}", headers=sam)).status_code == 404
    assert (await client.patch(f"/api/v1/study-aids/{deck['id']}/progress", json={"known": [0]}, headers=sam)).status_code == 404
    assert (await client.delete(f"/api/v1/study-aids/{deck['id']}", headers=sam)).status_code == 404
    assert (await client.get(f"/api/v1/study-aids/{deck['id']}", headers=alex)).status_code == 200


async def test_the_daily_allowance_counts_all_kinds_together(client: AsyncClient, db_session: AsyncSession, aid_limit) -> None:
    aid_limit.rate_limit_study_aids_per_day = 2
    headers = await _sign_in(db_session, "a@example.com")
    series_id = await _series(client, headers)
    await _make(client, headers, series_id, "guide")
    await _make(client, headers, series_id, "flashcards")
    refused = await client.post(f"/api/v1/series/{series_id}/study-aids", json={"kind": "cheatsheet"}, headers=headers)
    assert refused.status_code == 429
    assert "study aids" in refused.json()["detail"]


# --- flashcard progress -----------------------------------------------------------


async def test_flashcard_progress_is_saved_and_validated(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _sign_in(db_session, "a@example.com")
    series_id = await _series(client, headers)
    deck = await _make(client, headers, series_id, "flashcards")
    guide = await _make(client, headers, series_id, "guide")
    url = f"/api/v1/study-aids/{deck['id']}/progress"

    saved = await client.patch(url, json={"known": [5, 0, 2]}, headers=headers)
    assert saved.status_code == 200
    assert (saved.json()["known"], saved.json()["known_count"]) == ([0, 2, 5], 3)
    summary = next(aid for aid in await _listed(client, headers, series_id) if aid["kind"] == "flashcards")
    assert (summary["card_count"], summary["known_count"]) == (8, 3)

    assert (await client.patch(url, json={"known": [8]}, headers=headers)).status_code == 422  # no such card
    assert (await client.patch(url, json={"known": [-1]}, headers=headers)).status_code == 422
    assert (await client.patch(url, json={"known": [1, 1]}, headers=headers)).status_code == 422
    assert (await client.patch(f"/api/v1/study-aids/{guide['id']}/progress", json={"known": []}, headers=headers)).status_code == 422
    assert (await client.patch(url, json={"known": []}, headers=headers)).json()["known"] == []  # start over


# --- cleanup ------------------------------------------------------------------------


async def test_study_aids_go_with_cleanup_the_series_and_the_account(
    client: AsyncClient, db_session: AsyncSession, aid_limit
) -> None:
    aid_limit.rate_limit_study_aids_per_day = 10  # this test is about cleanup, not the allowance
    headers = await _sign_in(db_session, "a@example.com")
    lam = await _series(client, headers, "white", LAMBDA)
    dp = await _series(client, headers, "red", "Dynamic Programming")
    old = await _make(client, headers, lam, "guide")
    await _make(client, headers, lam, "flashcards")
    keep = await _make(client, headers, dp, "cheatsheet")

    await db_session.execute(
        update(StudyAid).where(StudyAid.id == uuid.UUID(old["id"])).values(created_at=datetime.now(UTC) - timedelta(days=45))
    )
    await db_session.commit()
    assert (await client.post("/api/v1/maintenance/cleanup", headers=API_KEY)).status_code == 200
    assert [aid["kind"] for aid in await _listed(client, headers, lam)] == ["flashcards"]

    assert (await client.delete(f"/api/v1/series/{lam}", headers=headers)).status_code == 204
    assert [str(i) for i in (await db_session.execute(select(StudyAid.id))).scalars().all()] == [keep["id"]]

    assert (await client.delete(f"/api/v1/study-aids/{keep['id']}", headers=headers)).status_code == 204
    await _make(client, headers, dp, "guide")
    assert (await client.delete("/api/v1/auth/account", headers=headers)).status_code == 204
    assert (await db_session.execute(select(StudyAid.id))).scalars().all() == []


# --- ClaudeStudyAidGenerator ----------------------------------------------------------

_SOURCE = SeriesText(category="Functional Programming", title=LAMBDA, slides=["syntax", "beta reduction"])


def _response(text: str, stop_reason: str = "end_turn") -> SimpleNamespace:
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], stop_reason=stop_reason)


def test_card_count_follows_the_series_size_within_bounds() -> None:
    assert card_count(SeriesText("C", "T", ["a"])) == 8
    assert card_count(SeriesText("C", "T", ["a"] * 3)) == 12
    assert card_count(SeriesText("C", "T", ["a"] * 12)) == MAX_CARDS


def test_cards_missing_a_side_are_dropped() -> None:
    cards = parse_cards({"cards": [{"front": " Q1? ", "back": " A1 "}, {"front": "Q2?", "back": "  "}, {"front": "", "back": "A3"}]})
    assert [(c.front, c.back) for c in cards] == [("Q1?", "A1")]
    with pytest.raises(ValueError):
        parse_cards({"cards": [{"front": " ", "back": "x"}]})
    assert len(parse_cards({"cards": [{"front": "q", "back": "a"}] * 30})) == MAX_CARDS


async def test_a_guide_is_plain_markdown_from_its_own_prompt() -> None:
    fake_client = streaming_client(_response("## The big picture\nLambda calculus is..."))
    aid = await ClaudeStudyAidGenerator(client=fake_client, model="claude-haiku-5-5").generate("guide", _SOURCE)

    assert (aid.title, aid.cards) == ("Lambda Calculus study guide", None)
    assert aid.markdown.startswith("## The big picture")
    call = fake_client.messages.stream.call_args.kwargs
    assert call["system"].startswith("You write a study guide")
    assert "format" not in call["output_config"]
    assert "[Slide 2]\nbeta reduction" in call["messages"][0]["content"]


async def test_flashcards_use_structured_output_and_ask_for_a_count() -> None:
    fake_client = streaming_client(_response(json.dumps({"cards": [{"front": "What is a redex?", "back": "A reducible expression."}]})))
    aid = await ClaudeStudyAidGenerator(client=fake_client, model="claude-haiku-5-5").generate("flashcards", _SOURCE)

    assert aid.markdown is None and [(c.front, c.back) for c in aid.cards] == [("What is a redex?", "A reducible expression.")]
    call = fake_client.messages.stream.call_args.kwargs
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert call["messages"][0]["content"].endswith("Write 8 cards.")


async def test_a_cut_off_answer_is_an_error_not_half_a_guide() -> None:
    fake_client = streaming_client(_response("## The big pic", stop_reason="max_tokens"))
    with pytest.raises(ValueError):
        await ClaudeStudyAidGenerator(client=fake_client, model="claude-haiku-5-5").generate("cheatsheet", _SOURCE)


# --- a long series ------------------------------------------------------------------


class _Recording:
    """Keeps the slides it was asked to write from."""

    model_name = "recording"

    def __init__(self) -> None:
        self.sources: list[SeriesText] = []

    async def generate(self, kind: str, source: SeriesText) -> GeneratedAid:
        self.sources.append(source)
        return GeneratedAid(title="t", markdown="## x") if kind != "flashcards" else GeneratedAid(title="t", cards=[Card("q", "a")])


async def test_a_study_aid_is_written_from_every_slide_of_a_long_series(
    client: AsyncClient, db_session: AsyncSession, aid_limit: None
) -> None:
    headers = await _sign_in(db_session, "a@example.com")
    series_id = await _series(client, headers)
    first = (await db_session.execute(select(Slide))).scalar_one()
    count = 20
    for n in range(1, count):
        db_session.add(
            Slide(
                presentation_id=first.presentation_id,
                slide_number=n + 1,
                image_hash=f"{n:064d}",
                status="analyzed",
                summary=f"Summary {n}",
                series_id=first.series_id,
                content_kind="lecture",
                created_at=datetime.now(UTC) + timedelta(seconds=n),
            )
        )
    await db_session.commit()

    recorder = _Recording()
    app.dependency_overrides[get_study_aid_generator] = lambda: recorder
    for kind in ("guide", "cheatsheet", "flashcards"):
        await _make(client, headers, series_id, kind)
    assert [len(source.slides) for source in recorder.sources] == [count, count, count]
    assert recorder.sources[0].slides[-1].startswith(f"Summary {count - 1}")  # in capture order
