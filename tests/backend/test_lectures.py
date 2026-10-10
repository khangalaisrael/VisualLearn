"""Capture history: lecture grouping on analyze, GET /lectures, re-opening a
capture, deleting a capture or lecture, and the cleaned lecture metadata."""

import io
import uuid
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from PIL import Image
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orm import Conversation, Presentation, Slide, User
from app.models.orm import Session as SessionRow
from app.services.lecture_meta import clean_page_url, clean_title, lecture_key

API_KEY = {"X-API-Key": "test-api-key"}
LECTURE_URL = "https://learn.uct.ac.za/lectures/csc2001/lecture-1?token=secret#slide=4"


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


async def _capture(
    client: AsyncClient,
    headers: dict[str, str],
    color: str,
    *,
    title: str | None = "CSC2001 lecture 1",
    url: str | None = LECTURE_URL,
    presentation_id: str | None = None,
) -> dict:
    data = {"slide_number": "1"}
    if title is not None:
        data["lecture_title"] = title
    if url is not None:
        data["page_url"] = url
    if presentation_id is not None:
        data["presentation_id"] = presentation_id
    response = await client.post(
        "/api/v1/slides/analyze",
        files={"image": ("slide.png", _png(color), "image/png")},
        data=data,
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _chat(client: AsyncClient, headers: dict[str, str], captured: dict, message: str) -> str:
    response = await client.post(
        "/api/v1/chat",
        json={
            "conversation_id": None,
            "presentation_id": captured["presentation_id"],
            "query_mode": "slide",
            "slide_id": captured["slide_id"],
            "object_id": None,
            "message": message,
        },
        headers=headers,
    )
    assert response.status_code == 200
    return response.text.split('"conversation_id": "')[1].split('"')[0]


# --- metadata cleaning --------------------------------------------------------


def test_page_url_drops_query_fragment_and_credentials() -> None:
    assert clean_page_url("https://user:pw@Example.com:8443/a/b?token=1#x") == "https://example.com:8443/a/b"
    assert clean_page_url("chrome://extensions") is None
    assert clean_page_url("not a url") is None
    assert clean_page_url(None) is None


def test_title_is_collapsed_trimmed_and_defaulted() -> None:
    assert clean_title("  CSC2001 \n  lecture   1 ") == "CSC2001 lecture 1"
    assert clean_title("   ") == "Untitled presentation"
    assert len(clean_title("x" * 1000)) == 255


def test_lecture_key_ignores_case() -> None:
    assert lecture_key("https://A.com/Deck") == lecture_key("https://a.com/deck")
    assert lecture_key(None) is None


# --- grouping on analyze ----------------------------------------------------


async def test_signed_in_captures_of_one_page_share_a_lecture(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _sign_in(db_session, "a@example.com")
    first = await _capture(client, headers, "white")
    second = await _capture(client, headers, "black", url="https://learn.uct.ac.za/lectures/csc2001/lecture-1?page=2")
    other = await _capture(client, headers, "red", title="MAT1000", url="https://example.com/maths")

    assert first["presentation_id"] == second["presentation_id"]
    assert other["presentation_id"] != first["presentation_id"]

    stored = (await db_session.execute(select(Presentation).where(Presentation.id == uuid.UUID(first["presentation_id"])))).scalar_one()
    assert stored.title == "CSC2001 lecture 1"
    assert stored.page_url == "https://learn.uct.ac.za/lectures/csc2001/lecture-1"  # no query, no fragment


async def test_an_explicit_presentation_id_is_still_honoured(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _sign_in(db_session, "a@example.com")
    first = await _capture(client, headers, "white")
    second = await _capture(client, headers, "black", url="https://example.com/else", presentation_id=first["presentation_id"])
    assert second["presentation_id"] == first["presentation_id"]


async def test_capture_without_metadata_still_works(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _sign_in(db_session, "a@example.com")
    captured = await _capture(client, headers, "white", title=None, url=None)
    stored = (await db_session.execute(select(Presentation).where(Presentation.id == uuid.UUID(captured["presentation_id"])))).scalar_one()
    assert stored.title == "Untitled presentation"
    assert stored.page_url is None


async def test_two_users_do_not_share_a_lecture(client: AsyncClient, db_session: AsyncSession) -> None:
    alex = await _sign_in(db_session, "alex@example.com")
    sam = await _sign_in(db_session, "sam@example.com")
    a = await _capture(client, alex, "white")
    s = await _capture(client, sam, "white")
    assert a["presentation_id"] != s["presentation_id"]


# --- GET /lectures ----------------------------------------------------------


async def test_lectures_requires_sign_in(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/lectures", headers=API_KEY)).status_code == 401


async def test_lectures_groups_captures_and_counts_follow_ups(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _sign_in(db_session, "a@example.com")
    first = await _capture(client, headers, "white")
    second = await _capture(client, headers, "black")
    await _capture(client, headers, "red", title="MAT1000", url="https://example.com/maths")
    conversation_id = await _chat(client, headers, first, "Explain this")
    # SQLite timestamps tie within a second; make "first" clearly the older one.
    await db_session.execute(
        update(Slide).where(Slide.id == uuid.UUID(first["slide_id"])).values(created_at=datetime.now(UTC) - timedelta(hours=1))
    )
    await db_session.commit()

    body = (await client.get("/api/v1/lectures", headers=headers)).json()
    assert body["retention_days"] == 30
    by_title = {lecture["title"]: lecture for lecture in body["lectures"]}
    assert set(by_title) == {"CSC2001 lecture 1", "MAT1000"}

    captures = by_title["CSC2001 lecture 1"]["captures"]
    assert [c["slide_id"] for c in captures] == [second["slide_id"], first["slide_id"]]  # newest first
    followed = next(c for c in captures if c["slide_id"] == first["slide_id"])
    assert [(c["id"], c["message_count"]) for c in followed["conversations"]] == [(conversation_id, 2)]
    assert next(c for c in captures if c["slide_id"] == second["slide_id"])["conversations"] == []


async def test_lectures_are_private_to_their_owner(client: AsyncClient, db_session: AsyncSession) -> None:
    alex = await _sign_in(db_session, "alex@example.com")
    sam = await _sign_in(db_session, "sam@example.com")
    await _capture(client, alex, "white")
    assert (await client.get("/api/v1/lectures", headers=sam)).json()["lectures"] == []


async def test_old_captures_are_hidden_from_the_list(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _sign_in(db_session, "a@example.com")
    await _capture(client, headers, "white")
    await db_session.execute(update(Slide).values(created_at=datetime.now(UTC) - timedelta(days=31)))
    await db_session.commit()
    assert (await client.get("/api/v1/lectures", headers=headers)).json()["lectures"] == []


# --- GET/DELETE /slides ------------------------------------------------------


async def test_a_capture_can_be_reopened_by_its_owner_only(client: AsyncClient, db_session: AsyncSession) -> None:
    alex = await _sign_in(db_session, "alex@example.com")
    sam = await _sign_in(db_session, "sam@example.com")
    captured = await _capture(client, alex, "white")

    reopened = await client.get(f"/api/v1/slides/{captured['slide_id']}", headers=alex)
    assert reopened.status_code == 200
    assert reopened.json()["slide_id"] == captured["slide_id"]
    assert (await client.get(f"/api/v1/slides/{captured['slide_id']}", headers=sam)).status_code == 404
    assert (await client.get(f"/api/v1/slides/{uuid.uuid4()}", headers=alex)).status_code == 404
    assert (await client.get("/api/v1/slides/not-a-uuid", headers=alex)).status_code == 404


async def test_deleting_a_capture_removes_its_chats(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _sign_in(db_session, "a@example.com")
    first = await _capture(client, headers, "white")
    second = await _capture(client, headers, "black")
    await _chat(client, headers, first, "Explain this")

    assert (await client.delete(f"/api/v1/slides/{first['slide_id']}", headers=headers)).status_code == 204
    assert (await client.get(f"/api/v1/slides/{first['slide_id']}", headers=headers)).status_code == 404
    assert (await client.get(f"/api/v1/slides/{second['slide_id']}", headers=headers)).status_code == 200
    assert (await db_session.execute(select(Conversation.id))).scalars().all() == []


async def test_others_cannot_delete_and_signed_out_cannot_delete(client: AsyncClient, db_session: AsyncSession) -> None:
    alex = await _sign_in(db_session, "alex@example.com")
    sam = await _sign_in(db_session, "sam@example.com")
    captured = await _capture(client, alex, "white")
    assert (await client.delete(f"/api/v1/slides/{captured['slide_id']}", headers=sam)).status_code == 404
    assert (await client.delete(f"/api/v1/slides/{captured['slide_id']}", headers=API_KEY)).status_code == 401
    assert (await client.get(f"/api/v1/slides/{captured['slide_id']}", headers=alex)).status_code == 200


async def test_deleting_a_lecture_removes_captures_and_chats(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _sign_in(db_session, "a@example.com")
    first = await _capture(client, headers, "white")
    await _capture(client, headers, "black")
    keep = await _capture(client, headers, "red", title="MAT1000", url="https://example.com/maths")
    await _chat(client, headers, first, "Explain this")

    assert (await client.delete(f"/api/v1/lectures/{first['presentation_id']}", headers=headers)).status_code == 204
    remaining = (await client.get("/api/v1/lectures", headers=headers)).json()["lectures"]
    assert [lecture["id"] for lecture in remaining] == [keep["presentation_id"]]
    assert (await db_session.execute(select(Conversation.id))).scalars().all() == []


async def test_deleting_someone_elses_lecture_is_a_404(client: AsyncClient, db_session: AsyncSession) -> None:
    alex = await _sign_in(db_session, "alex@example.com")
    sam = await _sign_in(db_session, "sam@example.com")
    captured = await _capture(client, alex, "white")
    assert (await client.delete(f"/api/v1/lectures/{captured['presentation_id']}", headers=sam)).status_code == 404
    assert (await client.delete(f"/api/v1/lectures/{captured['presentation_id']}", headers=API_KEY)).status_code == 401
    assert len((await client.get("/api/v1/lectures", headers=alex)).json()["lectures"]) == 1


# --- retention --------------------------------------------------------------


async def test_cleanup_keeps_a_lecture_that_still_has_recent_captures(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _sign_in(db_session, "a@example.com")
    old = await _capture(client, headers, "white")
    fresh = await _capture(client, headers, "black")
    long_ago = datetime.now(UTC) - timedelta(days=45)
    await db_session.execute(update(Presentation).values(created_at=long_ago))
    await db_session.execute(update(Slide).where(Slide.id == uuid.UUID(old["slide_id"])).values(created_at=long_ago))
    await db_session.commit()

    result = (await client.post("/api/v1/maintenance/cleanup", headers=API_KEY)).json()
    assert result["presentations"] == 0  # the lecture still has a recent capture

    slides = (await db_session.execute(select(Slide.id))).scalars().all()
    assert [str(s) for s in slides] == [fresh["slide_id"]]
