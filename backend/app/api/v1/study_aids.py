"""Study aids on a series: a study guide, a cheat sheet and a deck of flashcards.

POST /series/{id}/study-aids writes one (a model call, counted against a
daily allowance). A series holds at most one of each kind: writing it again
replaces the earlier one, and only once the new one exists. GET lists what a
series has; PATCH .../progress records which flashcards the student knows.
Like quizzes, study aids expire with the 30-day retention; a guide or cheat
sheet the student wants to keep is saved as a note.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import enforce_study_aid_rate_limit, get_current_user_id, get_study_aid_generator, verify_api_key
from app.db.session import get_db
from app.models.orm import Series, StudyAid
from app.models.schemas import (
    Flashcard,
    StudyAidCreateRequest,
    StudyAidListResponse,
    StudyAidOut,
    StudyAidProgressRequest,
    StudyAidSummary,
)
from app.repositories.usage_events import UsageEventRepository
from app.services.retention import retention_cutoff
from app.services.series_source import read_series
from app.services.study_aid_generator import StudyAidGenerator
from app.services.usage import estimate_cost_usd, start_accumulator

router = APIRouter(tags=["study aids"], dependencies=[Depends(verify_api_key)])


def _require_user(current_user_id: uuid.UUID | None) -> uuid.UUID:
    if current_user_id is None:
        raise HTTPException(status_code=401, detail="Sign in to make study guides and flashcards.")
    return current_user_id


def _parse(value: str, detail: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=detail) from exc


async def _owned_series(db: AsyncSession, series_id: str, user_id: uuid.UUID) -> Series:
    series = await db.get(Series, _parse(series_id, "Unknown series"))
    if series is None or series.user_id != user_id:
        raise HTTPException(status_code=404, detail="Unknown series")
    return series


async def _owned_aid(db: AsyncSession, aid_id: str, user_id: uuid.UUID) -> StudyAid:
    aid = await db.get(StudyAid, _parse(aid_id, "Unknown study aid"))
    if aid is None or aid.user_id != user_id:
        raise HTTPException(status_code=404, detail="Unknown study aid")
    return aid


def _summary(aid: StudyAid) -> dict:
    cards = aid.content.get("cards")
    return {
        "id": str(aid.id),
        "kind": aid.kind,
        "title": aid.title,
        "created_at": aid.created_at,
        "card_count": len(cards) if cards is not None else None,
        "known_count": len(aid.progress or []) if cards is not None else None,
    }


def _out(aid: StudyAid) -> StudyAidOut:
    cards = aid.content.get("cards")
    return StudyAidOut(
        **_summary(aid),
        series_id=str(aid.series_id),
        markdown=aid.content.get("markdown"),
        cards=[Flashcard(**card) for card in cards] if cards is not None else None,
        known=sorted(aid.progress or []),
    )


@router.post(
    "/series/{series_id}/study-aids",
    response_model=StudyAidOut,
    status_code=201,
    dependencies=[Depends(enforce_study_aid_rate_limit)],
)
async def create_study_aid(
    series_id: str,
    body: StudyAidCreateRequest,
    db: AsyncSession = Depends(get_db),
    generator: StudyAidGenerator = Depends(get_study_aid_generator),
    current_user_id: uuid.UUID | None = Depends(get_current_user_id),
) -> StudyAidOut:
    user_id = _require_user(current_user_id)
    series = await _owned_series(db, series_id, user_id)
    # The whole series, however long: a guide that left slides out would mislead.
    source = await read_series(db, series, max_slides=None)
    if source is None:
        raise HTTPException(status_code=422, detail="This series has no slides to write from.")

    usage = start_accumulator()
    try:
        generated = await generator.generate(body.kind, source.text)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="That could not be written. Please try again.") from exc

    content: dict = (
        {"cards": [{"front": card.front, "back": card.back} for card in generated.cards]}
        if generated.cards is not None
        else {"markdown": generated.markdown or ""}
    )
    # The earlier one of this kind goes only now that its replacement exists.
    await db.execute(
        delete(StudyAid).where(StudyAid.user_id == user_id, StudyAid.series_id == series.id, StudyAid.kind == body.kind)
    )
    aid = StudyAid(user_id=user_id, series_id=series.id, kind=body.kind, title=generated.title, content=content, progress=[])
    db.add(aid)
    await UsageEventRepository(db).record(
        user_id=user_id,
        action="study_aid",
        model=generator.model_name,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        est_cost_usd=estimate_cost_usd(generator.model_name, usage.input_tokens, usage.output_tokens),
    )
    await db.commit()
    await db.refresh(aid)
    return _out(aid)


@router.get("/series/{series_id}/study-aids", response_model=StudyAidListResponse)
async def list_study_aids(
    series_id: str,
    db: AsyncSession = Depends(get_db),
    current_user_id: uuid.UUID | None = Depends(get_current_user_id),
) -> StudyAidListResponse:
    user_id = _require_user(current_user_id)
    series = await _owned_series(db, series_id, user_id)
    aids = (
        await db.execute(
            select(StudyAid)
            .where(StudyAid.user_id == user_id, StudyAid.series_id == series.id, StudyAid.created_at >= retention_cutoff())
            .order_by(StudyAid.created_at.desc())
        )
    ).scalars()
    return StudyAidListResponse(aids=[StudyAidSummary(**_summary(aid)) for aid in aids])


@router.get("/study-aids/{aid_id}", response_model=StudyAidOut)
async def get_study_aid(
    aid_id: str,
    db: AsyncSession = Depends(get_db),
    current_user_id: uuid.UUID | None = Depends(get_current_user_id),
) -> StudyAidOut:
    return _out(await _owned_aid(db, aid_id, _require_user(current_user_id)))


@router.patch("/study-aids/{aid_id}/progress", response_model=StudyAidOut)
async def update_progress(
    aid_id: str,
    body: StudyAidProgressRequest,
    db: AsyncSession = Depends(get_db),
    current_user_id: uuid.UUID | None = Depends(get_current_user_id),
) -> StudyAidOut:
    aid = await _owned_aid(db, aid_id, _require_user(current_user_id))
    cards = aid.content.get("cards")
    if cards is None:
        raise HTTPException(status_code=422, detail="Only flashcards have progress")
    known = set(body.known)
    if len(known) != len(body.known) or any(not 0 <= index < len(cards) for index in known):
        raise HTTPException(status_code=422, detail="known must list distinct card positions in this deck")
    aid.progress = sorted(known)
    await db.commit()
    await db.refresh(aid)
    return _out(aid)


@router.delete("/study-aids/{aid_id}", status_code=204)
async def delete_study_aid(
    aid_id: str,
    db: AsyncSession = Depends(get_db),
    current_user_id: uuid.UUID | None = Depends(get_current_user_id),
) -> None:
    aid = await _owned_aid(db, aid_id, _require_user(current_user_id))
    await db.delete(aid)
    await db.commit()
