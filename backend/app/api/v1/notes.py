"""Study notes: answers a signed-in user saved, and notes they wrote.

GET /notes lists them, POST creates one, PATCH edits its title or text,
DELETE removes it. Notes are kept until deleted (the 30-day retention does
not apply). Another user's note is a 404, same as an unknown id.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id, verify_api_key
from app.core.config import get_settings
from app.db.session import get_db
from app.models.orm import Note, Presentation, Series, Slide
from app.models.schemas import NoteCreateRequest, NoteListResponse, NoteOut, NoteUpdateRequest

router = APIRouter(tags=["notes"], dependencies=[Depends(verify_api_key)])

_UNTITLED = "Untitled note"


def _require_user(current_user_id: uuid.UUID | None) -> uuid.UUID:
    if current_user_id is None:
        raise HTTPException(status_code=401, detail="Sign in to keep notes.")
    return current_user_id


def _parse(value: str, detail: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=detail) from exc


def _title(title: str, body: str) -> str:
    """A blank title becomes the note's first line."""
    cleaned = " ".join(title.split())
    if cleaned:
        return cleaned
    first_line = next((line.strip(" #*") for line in body.splitlines() if line.strip(" #*")), "")
    return first_line[:80] or _UNTITLED


def _out(note: Note, topic: str | None) -> NoteOut:
    return NoteOut(
        id=str(note.id),
        title=note.title,
        body=note.body,
        source="ai" if note.source == "ai" else "user",
        topic=topic,
        series_id=str(note.series_id) if note.series_id else None,
        slide_id=str(note.slide_id) if note.slide_id else None,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


async def _owned(db: AsyncSession, note_id: str, user_id: uuid.UUID) -> Note:
    note = await db.get(Note, _parse(note_id, "Unknown note"))
    if note is None or note.user_id != user_id:
        raise HTTPException(status_code=404, detail="Unknown note")
    return note


async def _current_topic(db: AsyncSession, note: Note) -> str | None:
    series = await db.get(Series, note.series_id) if note.series_id else None
    return series.title if series is not None else note.topic


@router.get("/notes", response_model=NoteListResponse)
async def list_notes(
    db: AsyncSession = Depends(get_db),
    current_user_id: uuid.UUID | None = Depends(get_current_user_id),
) -> NoteListResponse:
    user_id = _require_user(current_user_id)
    notes = list(
        (await db.execute(select(Note).where(Note.user_id == user_id).order_by(Note.updated_at.desc()))).scalars()
    )
    titles = {
        series_id: title
        for series_id, title in (
            await db.execute(select(Series.id, Series.title).where(Series.user_id == user_id))
        ).all()
    }
    return NoteListResponse(notes=[_out(note, titles.get(note.series_id, note.topic)) for note in notes])


@router.post("/notes", response_model=NoteOut, status_code=201)
async def create_note(
    body: NoteCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user_id: uuid.UUID | None = Depends(get_current_user_id),
) -> NoteOut:
    user_id = _require_user(current_user_id)
    count = (await db.execute(select(func.count(Note.id)).where(Note.user_id == user_id))).scalar_one()
    if count >= get_settings().max_notes_per_user:
        raise HTTPException(status_code=409, detail="You've reached the note limit. Delete a note to add another.")

    slide: Slide | None = None
    if body.slide_id is not None:
        slide = await db.get(Slide, _parse(body.slide_id, "Unknown slide"))
        presentation = await db.get(Presentation, slide.presentation_id) if slide is not None else None
        if slide is None or presentation is None or presentation.user_id != user_id:
            raise HTTPException(status_code=404, detail="Unknown slide")

    series_id = _parse(body.series_id, "Unknown series") if body.series_id else (slide.series_id if slide else None)
    series = await db.get(Series, series_id) if series_id is not None else None
    if series_id is not None and (series is None or series.user_id != user_id):
        raise HTTPException(status_code=404, detail="Unknown series")

    note = Note(
        user_id=user_id,
        series_id=series.id if series else None,
        slide_id=slide.id if slide else None,
        topic=series.title if series else None,
        title=_title(body.title, body.body),
        body=body.body,
        source=body.source,
    )
    db.add(note)
    await db.commit()
    await db.refresh(note)
    return _out(note, note.topic)


@router.patch("/notes/{note_id}", response_model=NoteOut)
async def update_note(
    note_id: str,
    body: NoteUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user_id: uuid.UUID | None = Depends(get_current_user_id),
) -> NoteOut:
    note = await _owned(db, note_id, _require_user(current_user_id))
    if body.body is not None:
        note.body = body.body
    if body.title is not None:
        note.title = _title(body.title, note.body)
    note.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(note)
    return _out(note, await _current_topic(db, note))


@router.delete("/notes/{note_id}", status_code=204)
async def delete_note(
    note_id: str,
    db: AsyncSession = Depends(get_db),
    current_user_id: uuid.UUID | None = Depends(get_current_user_id),
) -> None:
    note = await _owned(db, note_id, _require_user(current_user_id))
    await db.delete(note)
    await db.commit()
