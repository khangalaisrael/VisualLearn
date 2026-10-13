"""The course brain: general chat answered from the student's own captured
slides and notes (services/course_library.py), searched by BM25 so only the
few matching ones are sent to the model."""

import json
import uuid
from datetime import UTC, datetime, timedelta

from conftest import FakeChatService
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orm import Note, ObjectRecord, Presentation, Series, Slide, User
from app.models.orm import Session as SessionRow
from app.services.course_library import LibraryDoc, build_context, rank, tokenize

API_KEY = {"X-API-Key": "test-api-key"}


async def _user(db: AsyncSession, email: str) -> tuple[uuid.UUID, dict[str, str]]:
    user = User(id=uuid.uuid4(), google_sub=f"sub-{email}", email=email)
    db.add(user)
    await db.flush()
    token = f"token-{email}"
    db.add(SessionRow(id=uuid.uuid4(), user_id=user.id, token=token, expires_at=datetime.now(UTC) + timedelta(days=1)))
    await db.commit()
    return user.id, {**API_KEY, "Authorization": f"Bearer {token}"}


async def _slide(db: AsyncSession, user_id: uuid.UUID, series: Series | None, subtopic: str, summary: str, text: str) -> Slide:
    presentation = Presentation(id=uuid.uuid4(), user_id=user_id, title="Lecture", source_type="live_capture")
    db.add(presentation)
    slide = Slide(
        id=uuid.uuid4(),
        presentation_id=presentation.id,
        slide_number=1,
        image_hash=uuid.uuid4().hex,
        status="analyzed",
        summary=summary,
        series_id=series.id if series else None,
        subtopic=subtopic,
    )
    db.add(slide)
    db.add(ObjectRecord(id=uuid.uuid4(), slide_id=slide.id, type="paragraph", bounding_box={}, extracted_text=text, confidence=0.9))
    await db.commit()
    return slide


async def _chat(client: AsyncClient, headers: dict[str, str], message: str, **fields):
    return await client.post(
        "/api/v1/chat",
        json={"conversation_id": None, "presentation_id": None, "query_mode": "general", "slide_id": None, "object_id": None, "message": message, **fields},
        headers=headers,
    )


def _done(response) -> dict:
    line = next(line for line in response.text.split("\n") if line.startswith("data: ") and '"conversation_id"' in line)
    return json.loads(line.removeprefix("data: "))


def test_tokenize_drops_common_words_and_keeps_terms() -> None:
    assert tokenize("Why is merge sort O(n log n)?") == ["merge", "sort", "log"]
    assert tokenize("What's a monad in Haskell") == ["what's", "monad", "haskell"]


def test_rank_puts_the_best_match_first_and_returns_nothing_without_a_match() -> None:
    docs = [
        LibraryDoc(kind="slide", title="Eigenvalues", text="det(A - lambda I) = 0, eigenvectors of a matrix"),
        LibraryDoc(kind="slide", title="Merge Sort", text="split the array, sort each half, merge in linear time"),
        LibraryDoc(kind="note", title="Recurrences", text="merge sort T(n) = 2T(n/2) + n solves to n log n"),
    ]
    assert [doc.title for doc in rank(docs, "how does merge sort work")] == ["Merge Sort", "Recurrences"]
    assert rank(docs, "photosynthesis in plants") == []
    assert rank(docs, "what is it") == []  # only common words


def test_build_context_cites_slides_and_notes_and_says_when_nothing_matched() -> None:
    slide_id, note_id = uuid.uuid4(), uuid.uuid4()
    block, sources = build_context(
        [
            LibraryDoc(kind="slide", title="Merge Sort", text="merge in linear time", slide_id=slide_id, series_title="Divide and Conquer", subtopic="Merge Sort"),
            LibraryDoc(kind="note", title='My "merge" note', text="stable sort", note_id=note_id),
        ],
        library_size=5,
    )
    assert '<slide ref="S1" title="Divide and Conquer · Merge Sort">' in block
    assert "<note ref=\"N1\" title=\"My 'merge' note\">" in block
    assert [(s.ref, s.kind, s.slide_id, s.note_id) for s in sources] == [("S1", "slide", str(slide_id), None), ("N1", "note", None, str(note_id))]

    empty, none = build_context([], library_size=5)
    assert "Nothing in the student's captured slides or notes matches" in empty and none == []
    fresh, _ = build_context([], library_size=0)
    assert "has not captured any slides" in fresh


async def test_general_chat_with_library_answers_from_the_students_own_slides(client: AsyncClient, db_session: AsyncSession) -> None:
    user_id, headers = await _user(db_session, "a@example.com")
    series = Series(id=uuid.uuid4(), user_id=user_id, category="Algorithms", title="Divide and Conquer")
    db_session.add(series)
    await db_session.commit()
    mine = await _slide(db_session, user_id, series, "Merge Sort", "Merge sort halves the array.", "merge the two sorted halves in linear time")
    await _slide(db_session, user_id, None, "Eigenvalues", "Eigenvalues of a matrix.", "det(A - lambda I) = 0")
    db_session.add(Note(id=uuid.uuid4(), user_id=user_id, title="Merge sort is stable", body="ties take the left element", source="user"))
    # Someone else's slide on the same topic must never be used.
    other_id, _ = await _user(db_session, "b@example.com")
    await _slide(db_session, other_id, None, "Merge Sort (other student)", "Their merge sort.", "SECRET other student's merge sort notes")
    await db_session.commit()

    response = await _chat(client, headers, "How does merge sort work?", library=True)
    assert response.status_code == 200, response.text

    prompt = FakeChatService.captured_system_prompts[-1]
    assert prompt.startswith("You are VisionLearn, a STEM tutor for university students. This chat knows the student's course")
    assert "merge the two sorted halves in linear time" in prompt
    assert "ties take the left element" in prompt
    assert "det(A - lambda I)" not in prompt  # not about the question
    assert "SECRET" not in prompt

    sources = _done(response)["sources"]
    assert sources[0] == {"ref": "S1", "kind": "slide", "title": "Divide and Conquer · Merge Sort", "slide_id": str(mine.id), "note_id": None}
    assert [source["kind"] for source in sources] == ["slide", "note"]


async def test_a_follow_up_still_finds_the_slides_the_chat_is_about(client: AsyncClient, db_session: AsyncSession) -> None:
    user_id, headers = await _user(db_session, "c@example.com")
    await _slide(db_session, user_id, None, "Master Theorem", "The Master Theorem for recurrences.", "T(n) = aT(n/b) + f(n), three cases")
    first = await _chat(client, headers, "Explain the master theorem", library=True)
    conversation_id = _done(first)["conversation_id"]

    await _chat(client, headers, "and case 2?", library=True, conversation_id=conversation_id)
    assert "T(n) = aT(n/b) + f(n)" in FakeChatService.captured_system_prompts[-1]


async def test_without_the_flag_or_signed_out_general_chat_is_unchanged(client: AsyncClient, db_session: AsyncSession) -> None:
    user_id, headers = await _user(db_session, "d@example.com")
    await _slide(db_session, user_id, None, "Merge Sort", "Merge sort.", "merge in linear time")

    response = await _chat(client, headers, "How does merge sort work?")
    assert "sources" not in _done(response)
    assert FakeChatService.captured_system_prompts[-1].startswith("You are VisionLearn, a STEM tutor for university students. This is an open chat")

    signed_out = await _chat(client, API_KEY, "How does merge sort work?", library=True)
    assert signed_out.status_code == 200
    assert "<course_library>" not in FakeChatService.captured_system_prompts[-1]
