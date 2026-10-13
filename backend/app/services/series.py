"""Sorting a signed-in user's captures into series, and keeping series tidy.

`assign_series` never raises: a capture the sorter cannot place (a timeout,
a provider error) simply stays unsorted and is picked up the next time the
list is loaded (api/v1/series.py).
"""

import asyncio
import logging
import re
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, exists, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.orm import Note, ObjectRecord, Presentation, Quiz, Series, Slide, StudyAid
from app.models.schemas import SeriesRef
from app.repositories.objects import ObjectRepository
from app.repositories.usage_events import UsageEventRepository
from app.services.series_sorter import (
    MAX_EXISTING_SERIES,
    ExistingSeries,
    PreviousCapture,
    SeriesSorter,
    SlideDigest,
)
from app.services.usage import estimate_cost_usd, start_accumulator

logger = logging.getLogger(__name__)

_MAX_HEADINGS = 4
# How many of a series' subtopics the sorter is shown.
_MAX_SUBTOPICS = 5
# A capture older than this no longer says where the next one belongs.
_PREVIOUS_CAPTURE_MINUTES = 90
# A capture this soon after a lecture slide from the same page continues that
# slide's series without asking the sorter (see _follow_on).
_FOLLOW_ON_MINUTES = 20
_SUBTOPIC_CHARS = 120
# A heading like these may start the exercises at the end of a lecture, which
# the sorter files as "practice": such slides are always given to the sorter.
_PRACTICE_HEADING = re.compile(
    r"\b(exercises?|practice|problems?|questions?|quiz|tutorial|homework|assignments?|worksheet|your turn|try it)\b",
    re.IGNORECASE,
)
# The sorter may widen a series' title only while the series is this new:
# it was named after its first slide, before the rest of the lecture was
# seen. Later the name is the student's to keep or change.
_RETITLE_WINDOW = timedelta(hours=3)


def digest_slide(slide: Slide, objects: Sequence[ObjectRecord], page_title: str) -> SlideDigest:
    headings = [o.extracted_text for o in objects if o.type == "title" and o.extracted_text][:_MAX_HEADINGS]
    text = " ".join(o.extracted_text for o in objects if o.type in ("paragraph", "equation", "code") and o.extracted_text)
    return SlideDigest(page_title=page_title, summary=slide.summary or "", headings=headings, text=text)


def series_ref(series: Series | None, slide: Slide) -> SeriesRef | None:
    if series is None:
        return None
    return SeriesRef(
        id=str(series.id),
        category=series.category,
        title=series.title,
        subtopic=slide.subtopic,
        kind=slide.content_kind or "lecture",
    )


async def list_series(db: AsyncSession, user_id: uuid.UUID) -> list[Series]:
    """Most recently used first."""
    result = await db.execute(select(Series).where(Series.user_id == user_id).order_by(Series.updated_at.desc()))
    return list(result.scalars())


async def _subtopics_by_series(
    db: AsyncSession, series_ids: list[uuid.UUID], before: Slide | None = None
) -> dict[uuid.UUID, tuple[str, ...]]:
    """A few distinct subtopics per series, newest first; with `before`,
    only of slides captured ahead of that one."""
    if not series_ids:
        return {}
    query = select(Slide.series_id, Slide.subtopic).where(
        Slide.series_id.in_(series_ids), Slide.subtopic.is_not(None)
    )
    if before is not None:
        query = query.where(Slide.id != before.id, Slide.created_at <= before.created_at)
    rows = await db.execute(query.order_by(Slide.created_at.desc()))
    found: dict[uuid.UUID, list[str]] = {}
    for series_id, subtopic in rows:
        kept = found.setdefault(series_id, [])
        if len(kept) < _MAX_SUBTOPICS and subtopic not in kept:
            kept.append(subtopic)
    return {series_id: tuple(kept) for series_id, kept in found.items()}


def _as_utc(moment: datetime) -> datetime:
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


async def _previous_capture(
    db: AsyncSession, user_id: uuid.UUID, slide: Slide, shown: list[Series]
) -> PreviousCapture | None:
    """The user's last sorted capture before this slide, if it was recent."""
    made_at = _as_utc(slide.created_at) if slide.created_at is not None else datetime.now(UTC)
    row = (
        await db.execute(
            select(Slide)
            .join(Presentation, Presentation.id == Slide.presentation_id)
            .where(
                Presentation.user_id == user_id,
                Slide.id != slide.id,
                Slide.series_id.is_not(None),
                Slide.created_at <= made_at,
            )
            .order_by(Slide.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    minutes = int((made_at - _as_utc(row.created_at)).total_seconds() // 60)
    index = next((i for i, series in enumerate(shown) if series.id == row.series_id), None)
    if index is None or minutes > _PREVIOUS_CAPTURE_MINUTES:
        return None
    return PreviousCapture(
        existing_index=index,
        subtopic=row.subtopic or "",
        minutes_ago=max(minutes, 0),
        same_page=row.presentation_id == slide.presentation_id,
    )


async def _follow_on(
    db: AsyncSession, user_id: uuid.UUID, slide: Slide, objects: Sequence[ObjectRecord], shown: list[Series]
) -> tuple[Series, str] | None:
    """The series and subtopic for a slide whose place is not in doubt, so the
    sorter's model call can be skipped: the student's previous capture was a
    lecture slide on the same page, minutes ago, and this slide has a heading
    of its own that does not look like the start of exercises. The heading
    becomes the subtopic, as the sorter would make it. Anything less certain
    goes to the sorter."""
    heading = next((" ".join(o.extracted_text.split()) for o in objects if o.type == "title" and o.extracted_text), "")
    if not heading or _PRACTICE_HEADING.search(heading):
        return None
    made_at = _as_utc(slide.created_at) if slide.created_at is not None else datetime.now(UTC)
    previous = (
        await db.execute(
            select(Slide)
            .join(Presentation, Presentation.id == Slide.presentation_id)
            .where(
                Presentation.user_id == user_id,
                Slide.id != slide.id,
                Slide.series_id.is_not(None),
                Slide.created_at <= made_at,
            )
            .order_by(Slide.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if (
        previous is None
        or previous.presentation_id != slide.presentation_id
        or (previous.content_kind or "lecture") != "lecture"
        or made_at - _as_utc(previous.created_at) > timedelta(minutes=_FOLLOW_ON_MINUTES)
    ):
        return None
    series = next((s for s in shown if s.id == previous.series_id), None)
    if series is None:
        return None
    return series, heading[:_SUBTOPIC_CHARS]


async def find_or_create_series(db: AsyncSession, user_id: uuid.UUID, category: str, title: str) -> Series:
    """A new series whose name matches an existing one (ignoring case) joins it."""
    for series in await list_series(db, user_id):
        if series.title.lower() == title.lower() and series.category.lower() == category.lower():
            return series
    series = Series(user_id=user_id, category=category, title=title)
    db.add(series)
    await db.flush()
    return series


def place_slide(slide: Slide, series: Series, *, subtopic: str | None, kind: str) -> None:
    slide.series_id = series.id
    slide.subtopic = subtopic or None
    slide.content_kind = kind
    series.updated_at = datetime.now(UTC)
    if series.cover_slide_id is None:
        series.cover_slide_id = slide.id


def _widen_title(series: Series, title: str | None, all_series: list[Series], at: datetime) -> None:
    if not title or series.created_at is None or at - _as_utc(series.created_at) > _RETITLE_WINDOW:
        return
    taken = any(
        other.id != series.id
        and other.title.lower() == title.lower()
        and other.category.lower() == series.category.lower()
        for other in all_series
    )
    if not taken:
        series.title = title


async def assign_series(
    db: AsyncSession,
    sorter: SeriesSorter,
    *,
    user_id: uuid.UUID,
    slide: Slide,
    objects: Sequence[ObjectRecord],
    page_title: str,
    as_captured: bool = False,
) -> Series | None:
    """`as_captured` sorts the slide as if it had just been captured: only
    series that already held an earlier slide are offered, so sorting old
    captures again (`resort_slides`) is not steered by where they were."""
    all_series = await list_series(db, user_id)
    if as_captured:
        earlier = set(
            (
                await db.execute(
                    select(Slide.series_id).where(
                        Slide.series_id.in_([s.id for s in all_series]),
                        Slide.id != slide.id,
                        Slide.created_at <= slide.created_at,
                    )
                )
            ).scalars()
        )
        all_series = [s for s in all_series if s.id in earlier]
    shown = all_series[:MAX_EXISTING_SERIES]

    # The next slide of the lecture being captured: no model call needed.
    if not as_captured:
        follow = await _follow_on(db, user_id, slide, objects, shown)
        if follow is not None:
            series, subtopic = follow
            place_slide(slide, series, subtopic=subtopic, kind="lecture")
            await db.flush()
            logger.info("series_sort_skipped slide_id=%s series_id=%s", slide.id, series.id)
            return series

    usage = start_accumulator()
    try:
        subtopics = await _subtopics_by_series(db, [s.id for s in shown], slide if as_captured else None)
        previous = await _previous_capture(db, user_id, slide, shown)
        decision = await asyncio.wait_for(
            sorter.sort(
                digest_slide(slide, objects, page_title),
                [
                    ExistingSeries(category=s.category, title=s.title, subtopics=subtopics.get(s.id, ()))
                    for s in shown
                ],
                previous,
            ),
            timeout=get_settings().sort_timeout_seconds,
        )
    except Exception:
        logger.warning("series_sort_failed slide_id=%s", slide.id, exc_info=True)
        return None

    if decision.existing_index is not None:
        series = shown[decision.existing_index]
        _widen_title(
            series,
            decision.retitle,
            all_series,
            _as_utc(slide.created_at) if as_captured and slide.created_at is not None else datetime.now(UTC),
        )
    else:
        series = await find_or_create_series(db, user_id, decision.category, decision.title)
    place_slide(slide, series, subtopic=decision.subtopic, kind=decision.kind)

    await UsageEventRepository(db).record(
        user_id=user_id,
        action="sort",
        model=sorter.model_name,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        est_cost_usd=estimate_cost_usd(sorter.model_name, usage.input_tokens, usage.output_tokens),
        slide_id=slide.id,
    )
    await db.flush()
    return series


async def _carry_over(db: AsyncSession, emptied: uuid.UUID, target: uuid.UUID) -> None:
    """What was made for a series that has just lost its last slide follows
    that slide: its notes and quizzes, and each study aid the other series
    does not already have (it keeps one of each kind)."""
    await db.execute(update(Note).where(Note.series_id == emptied).values(series_id=target))
    await db.execute(update(Quiz).where(Quiz.series_id == emptied).values(series_id=target))
    kept = set((await db.execute(select(StudyAid.kind).where(StudyAid.series_id == target))).scalars())
    for aid in (await db.execute(select(StudyAid).where(StudyAid.series_id == emptied))).scalars():
        if aid.kind in kept:
            await db.delete(aid)
        else:
            aid.series_id = target
            kept.add(aid.kind)


async def resort_slides(
    db: AsyncSession,
    sorter: SeriesSorter,
    *,
    user_id: uuid.UUID,
    since: datetime,
    offset: int,
    limit: int,
) -> tuple[int, int]:
    """Sorts captures the user already has again, oldest first, a few per
    call: each is placed as if it had just been captured, after the ones
    before it. Returns how far the pass has got and how many there are. A
    slide the sorter cannot place stays where it was."""
    rows = (
        await db.execute(
            select(Slide, Presentation)
            .join(Presentation, Presentation.id == Slide.presentation_id)
            .where(Presentation.user_id == user_id, Slide.created_at >= since)
            .order_by(Slide.created_at, Slide.id)
        )
    ).all()
    objects = ObjectRepository(db)
    batch = rows[offset : offset + limit]
    for slide, presentation in batch:
        was = slide.series_id
        series = await assign_series(
            db,
            sorter,
            user_id=user_id,
            slide=slide,
            objects=await objects.list_by_slide(slide.id),
            page_title=presentation.title,
            as_captured=True,
        )
        if series is None or was is None or was == series.id:
            continue
        await db.execute(update(Note).where(Note.slide_id == slide.id).values(series_id=series.id))
        left = await db.scalar(select(func.count()).select_from(Slide).where(Slide.series_id == was))
        if not left:
            await _carry_over(db, was, series.id)
    await db.flush()
    await prune_series(db, user_id)
    return min(offset + len(batch), len(rows)), len(rows)


async def prune_series(db: AsyncSession, user_id: uuid.UUID) -> None:
    """After captures were deleted: drop the user's series that have none
    left, and give a series whose cover capture is gone its newest one."""
    await db.execute(
        delete(Series).where(Series.user_id == user_id, ~exists().where(Slide.series_id == Series.id))
    )
    for series in await list_series(db, user_id):
        cover = await db.get(Slide, series.cover_slide_id) if series.cover_slide_id is not None else None
        if cover is not None and cover.series_id == series.id:
            continue
        newest = await db.execute(
            select(Slide.id).where(Slide.series_id == series.id).order_by(Slide.created_at.desc()).limit(1)
        )
        series.cover_slide_id = newest.scalar_one_or_none()
    await db.flush()
