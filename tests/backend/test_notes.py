"""Notes: create, list, edit, delete, ownership, and that they outlive the
30-day cleanup and the capture they came from."""

import io
import uuid
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from PIL import Image
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.orm import Note, Slide, User
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


async def _capture(client: AsyncClient, headers: dict[str, str], title: str = "Lambda Calculus") -> dict:
    buffer = io.BytesIO()
    Image.new("RGB", (10, 10), color="white").save(buffer, format="PNG")
    response = await client.post(
        "/api/v1/slides/analyze",
        files={"image": ("slide.png", buffer.getvalue(), "image/png")},
        data={"slide_number": "1", "lecture_title": title, "page_url": "https://example.com/a"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _notes(client: AsyncClient, headers: dict[str, str]) -> list[dict]:
    response = await client.get("/api/v1/notes", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["notes"]


async def test_notes_require_sign_in(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/notes", headers=API_KEY)).status_code == 401
    assert (await client.post("/api/v1/notes", json={"body": "x"}, headers=API_KEY)).status_code == 401


async def test_a_saved_answer_is_filed_under_its_slides_series(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _sign_in(db_session, "a@example.com")
    captured = await _capture(client, headers)
    created = await client.post(
        "/api/v1/notes",
        json={"title": "What is beta reduction?", "body": "Substitute $N$ for $x$.", "source": "ai", "slide_id": captured["slide_id"]},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    note = created.json()
    assert (note["topic"], note["series_id"], note["source"]) == ("Lambda Calculus", captured["series"]["id"], "ai")
    assert note["category"] == "General"  # the series' category, to file the note under
    assert note["series_starred"] is False
    # Starring the series (as Recent does) shows on its notes too.
    await client.patch(f"/api/v1/series/{captured['series']['id']}", json={"starred": True}, headers=headers)
    assert (await _notes(client, headers))[0]["series_starred"] is True
    await client.patch(f"/api/v1/series/{captured['series']['id']}", json={"starred": False}, headers=headers)
    assert await _notes(client, headers) == [note]


async def test_a_blank_title_becomes_the_first_line(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _sign_in(db_session, "a@example.com")
    created = await client.post("/api/v1/notes", json={"body": "\n## Church numerals\nZero is..."}, headers=headers)
    assert created.json()["title"] == "Church numerals"
    assert created.json()["source"] == "user"
    assert created.json()["topic"] is None

    assert (await client.post("/api/v1/notes", json={"body": ""}, headers=headers)).status_code == 422
    assert (await client.post("/api/v1/notes", json={"body": "x" * 20_001}, headers=headers)).status_code == 422


async def test_a_note_can_be_edited_and_moves_to_the_top(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _sign_in(db_session, "a@example.com")
    first = (await client.post("/api/v1/notes", json={"title": "First", "body": "one"}, headers=headers)).json()
    await client.post("/api/v1/notes", json={"title": "Second", "body": "two"}, headers=headers)
    await db_session.execute(update(Note).values(updated_at=datetime.now(UTC) - timedelta(hours=1)))
    await db_session.commit()

    edited = await client.patch(
        f"/api/v1/notes/{first['id']}", json={"title": "First, revised", "body": "one, plus my own addition"}, headers=headers
    )
    assert edited.status_code == 200
    assert edited.json()["body"] == "one, plus my own addition"
    assert [n["title"] for n in await _notes(client, headers)] == ["First, revised", "Second"]


async def test_notes_are_private_to_their_owner(client: AsyncClient, db_session: AsyncSession) -> None:
    alex = await _sign_in(db_session, "alex@example.com")
    sam = await _sign_in(db_session, "sam@example.com")
    captured = await _capture(client, alex)
    note = (await client.post("/api/v1/notes", json={"body": "mine"}, headers=alex)).json()

    assert await _notes(client, sam) == []
    assert (await client.patch(f"/api/v1/notes/{note['id']}", json={"body": "x"}, headers=sam)).status_code == 404
    assert (await client.delete(f"/api/v1/notes/{note['id']}", headers=sam)).status_code == 404
    # Sam cannot attach a note to Alex's slide or series.
    for link in ({"slide_id": captured["slide_id"]}, {"series_id": captured["series"]["id"]}):
        assert (await client.post("/api/v1/notes", json={"body": "x", **link}, headers=sam)).status_code == 404
    assert (await client.delete(f"/api/v1/notes/{note['id']}", headers=alex)).status_code == 204
    assert await _notes(client, alex) == []


async def test_a_note_outlives_cleanup_and_its_capture(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _sign_in(db_session, "a@example.com")
    captured = await _capture(client, headers)
    await client.post("/api/v1/notes", json={"body": "keep me", "slide_id": captured["slide_id"]}, headers=headers)
    long_ago = datetime.now(UTC) - timedelta(days=90)
    await db_session.execute(update(Slide).values(created_at=long_ago))
    await db_session.execute(update(Note).values(created_at=long_ago, updated_at=long_ago))
    await db_session.commit()

    assert (await client.post("/api/v1/maintenance/cleanup", headers=API_KEY)).status_code == 200
    assert (await db_session.execute(select(Slide.id))).scalars().all() == []
    notes = await _notes(client, headers)
    assert [n["body"] for n in notes] == ["keep me"]
    assert notes[0]["topic"] == "Lambda Calculus"  # the series is gone; its name is remembered
    assert notes[0]["category"] is None


async def test_the_note_limit_and_account_deletion(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _sign_in(db_session, "a@example.com")
    settings = get_settings()
    original = settings.max_notes_per_user
    settings.max_notes_per_user = 2
    try:
        for _ in range(2):
            assert (await client.post("/api/v1/notes", json={"body": "x"}, headers=headers)).status_code == 201
        assert (await client.post("/api/v1/notes", json={"body": "x"}, headers=headers)).status_code == 409
    finally:
        settings.max_notes_per_user = original

    assert (await client.delete("/api/v1/auth/account", headers=headers)).status_code == 204
    assert (await db_session.execute(select(Note.id))).scalars().all() == []


async def test_privacy_page_says_notes_are_kept(client: AsyncClient) -> None:
    page = (await client.get("/privacy")).text
    assert "kept until you delete them" in page


async def test_a_note_can_be_starred_without_counting_as_an_edit(client: AsyncClient, db_session: AsyncSession) -> None:
    alex = await _sign_in(db_session, "alex@example.com")
    sam = await _sign_in(db_session, "sam@example.com")
    note = (await client.post("/api/v1/notes", json={"title": "Keep", "body": "one"}, headers=alex)).json()
    assert note["starred"] is False

    starred = await client.patch(f"/api/v1/notes/{note['id']}", json={"starred": True}, headers=alex)
    assert starred.status_code == 200
    assert starred.json()["starred"] is True
    assert starred.json()["updated_at"] == note["updated_at"]  # starring is not an edit
    assert (await _notes(client, alex))[0]["starred"] is True

    # Editing the text keeps the star; someone else cannot star it.
    edited = await client.patch(f"/api/v1/notes/{note['id']}", json={"body": "two"}, headers=alex)
    assert edited.json()["starred"] is True
    assert (await client.patch(f"/api/v1/notes/{note['id']}", json={"starred": False}, headers=sam)).status_code == 404
    assert (await client.patch(f"/api/v1/notes/{note['id']}", json={"starred": False}, headers=alex)).json()["starred"] is False
