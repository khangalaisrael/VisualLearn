"""The signed-in user's captures, sorted into topic series.

GET /series lists them (and places a few captures the sorter has not seen
yet); PATCH renames a series or changes its cover; POST /slides/{id}/move
corrects the sorter; DELETE removes a series with its captures and chats.
Another user's series or capture is a 404, same as an unknown id.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id, get_series_sorter, verify_api_key
from app.core.config import get_settings
from app.db.session import get_db
from app.models.orm import Presentation, Quiz, QuizAttempt, Series, Slide, StudyAid
from app.models.schemas import (
    CaptureConversation,
    MoveSlideRequest,
    SeriesCapture,
    SeriesListResponse,
    SeriesRef,
    SeriesSummary,
    SeriesUpdateRequest,
)
from app.repositories.objects import ObjectRepository
from app.services.captures import SUMMARY_PREVIEW_CHARS, conversations_by_slide
from app.services.presentations import delete_slides
from app.services.retention import retention_cutoff
from app.services.series import assign_series, find_or_create_series, place_slide, prune_series, series_ref
from app.services.series_sorter import SeriesSorter

router = APIRouter(tags=["series"], dependencies=[Depends(verify_api_key)])


def _require_user(current_user_id: uuid.UUID | None) -> uuid.UUID:
    if current_user_id is None:
        raise HTTPException(status_code=401, detail="Sign in to see your series.")
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


async def _owned_slide(db: AsyncSession, slide_id: str, user_id: uuid.UUID) -> Slide:
    slide = await db.get(Slide, _parse(slide_id, "Unknown slide"))
    presentation = await db.get(Presentation, slide.presentation_id) if slide is not None else None
    if slide is None or presentation is None or presentation.user_id != user_id:
        raise HTTPException(status_code=404, detail="Unknown slide")
    return slide


def _capture(slide: Slide, presentation: Presentation, chats: list[CaptureConversation]) -> SeriesCapture:
    return SeriesCapture(
        slide_id=str(slide.id),
        summary=(slide.summary or "")[:SUMMARY_PREVIEW_CHARS],
        subtopic=slide.subtopic,
        kind=slide.content_kind or "lecture",
        created_at=slide.created_at,
        page_title=presentation.title,
        page_url=presentation.page_url,
        conversations=chats,
    )


@router.get("/series", response_model=SeriesListResponse)
async def list_series(
    db: AsyncSession = Depends(get_db),
    sorter: SeriesSorter = Depends(get_series_sorter),
    current_user_id: uuid.UUID | None = Depends(get_current_user_id),
) -> SeriesListResponse:
    user_id = _require_user(current_user_id)
    since = retention_cutoff()
    settings = get_settings()

    rows = (
        await db.execute(
            select(Slide, Presentation)
            .join(Presentation, Presentation.id == Slide.presentation_id)
            .where(Presentation.user_id == user_id, Slide.created_at >= since)
            .order_by(Slide.created_at.desc())
        )
    ).all()

    # Captures from before sorting existed, or that the sorter missed: oldest
    # first, so a lecture's slides are filed in the order they were shown.
    pending = [(slide, presentation) for slide, presentation in rows if slide.series_id is None]
    objects = ObjectRepository(db)
    for slide, presentation in pending[::-1][: settings.sort_backfill_per_request]:
        await assign_series(
            db,
            sorter,
            user_id=user_id,
            slide=slide,
            objects=await objects.list_by_slide(slide.id),
            page_title=presentation.title,
        )
    if pending:
        await db.commit()

    chats = await conversations_by_slide(db, user_id, [slide.id for slide, _ in rows], since)
    series_rows = {
        s.id: s for s in (await db.execute(select(Series).where(Series.user_id == user_id))).scalars()
    }

    summaries: dict[uuid.UUID, SeriesSummary] = {}
    unsorted: list[SeriesCapture] = []
    for slide, presentation in rows:
        capture = _capture(slide, presentation, chats.get(slide.id, []))
        series = series_rows.get(slide.series_id) if slide.series_id is not None else None
        if series is None:
            unsorted.append(capture)
            continue
        summary = summaries.get(series.id)
        if summary is None:
            summary = summaries[series.id] = SeriesSummary(
                id=str(series.id),
                category=series.category,
                title=series.title,
                cover_slide_id=str(series.cover_slide_id) if series.cover_slide_id else None,
                starred=bool(series.starred),
                last_activity_at=slide.created_at,
                captures=[],
            )
        summary.captures.append(capture)
        # Chat activity counts toward when the series was last touched.
        for chat in capture.conversations:
            if chat.last_activity_at > summary.last_activity_at:
                summary.last_activity_at = chat.last_activity_at

    ordered = sorted(summaries.values(), key=lambda s: s.last_activity_at, reverse=True)
    return SeriesListResponse(retention_days=settings.chat_retention_days, series=ordered, unsorted=unsorted)


@router.patch("/series/{series_id}", status_code=204)
async def update_series(
    series_id: str,
    body: SeriesUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user_id: uuid.UUID | None = Depends(get_current_user_id),
) -> None:
    user_id = _require_user(current_user_id)
    series = await _owned_series(db, series_id, user_id)
    if body.title is not None:
        series.title = " ".join(body.title.split()) or series.title
    if body.category is not None:
        series.category = " ".join(body.category.split()) or series.category
    if body.starred is not None:
        series.starred = body.starred
    if body.cover_slide_id is not None:
        cover = await _owned_slide(db, body.cover_slide_id, user_id)
        if cover.series_id != series.id:
            raise HTTPException(status_code=422, detail="The cover must be a capture in this series")
        series.cover_slide_id = cover.id
    await db.commit()


@router.post("/slides/{slide_id}/move", response_model=SeriesRef)
async def move_slide(
    slide_id: str,
    body: MoveSlideRequest,
    db: AsyncSession = Depends(get_db),
    current_user_id: uuid.UUID | None = Depends(get_current_user_id),
) -> SeriesRef:
    user_id = _require_user(current_user_id)
    slide = await _owned_slide(db, slide_id, user_id)
    if body.series_id is not None:
        target = await _owned_series(db, body.series_id, user_id)
    elif body.category is not None and body.title is not None:
        target = await find_or_create_series(
            db, user_id, " ".join(body.category.split()), " ".join(body.title.split())
        )
    else:
        raise HTTPException(status_code=422, detail="Give a series_id, or a category and title for a new series")

    place_slide(slide, target, subtopic=slide.subtopic, kind=slide.content_kind or "lecture")
    await db.flush()
    await prune_series(db, user_id)
    await db.commit()
    ref = series_ref(target, slide)
    assert ref is not None
    return ref


@router.delete("/series/{series_id}", status_code=204)
async def delete_series(
    series_id: str,
    db: AsyncSession = Depends(get_db),
    current_user_id: uuid.UUID | None = Depends(get_current_user_id),
) -> None:
    user_id = _require_user(current_user_id)
    series = await _owned_series(db, series_id, user_id)
    slide_ids = list((await db.execute(select(Slide.id).where(Slide.series_id == series.id))).scalars())
    await delete_slides(db, slide_ids)
    quiz_ids = select(Quiz.id).where(Quiz.series_id == series.id)
    await db.execute(delete(QuizAttempt).where(QuizAttempt.quiz_id.in_(quiz_ids)))
    await db.execute(delete(Quiz).where(Quiz.series_id == series.id))
    await db.execute(delete(StudyAid).where(StudyAid.series_id == series.id))
    await prune_series(db, user_id)
    await db.commit()
