"""Sorting a signed-in user's captures into series, and keeping series tidy.

`assign_series` never raises: a capture the sorter cannot place (a timeout,
a provider error) simply stays unsorted and is picked up the next time the
list is loaded (api/v1/series.py).
"""

import asyncio
import logging
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import delete, exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.orm import ObjectRecord, Series, Slide
from app.models.schemas import SeriesRef
from app.repositories.usage_events import UsageEventRepository
from app.services.series_sorter import MAX_EXISTING_SERIES, ExistingSeries, SeriesSorter, SlideDigest
from app.services.usage import estimate_cost_usd, start_accumulator

logger = logging.getLogger(__name__)

_MAX_HEADINGS = 4


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


async def assign_series(
    db: AsyncSession,
    sorter: SeriesSorter,
    *,
    user_id: uuid.UUID,
    slide: Slide,
    objects: Sequence[ObjectRecord],
    page_title: str,
) -> Series | None:
    all_series = await list_series(db, user_id)
    shown = all_series[:MAX_EXISTING_SERIES]
    usage = start_accumulator()
    try:
        decision = await asyncio.wait_for(
            sorter.sort(
                digest_slide(slide, objects, page_title),
                [ExistingSeries(category=s.category, title=s.title) for s in shown],
            ),
            timeout=get_settings().sort_timeout_seconds,
        )
    except Exception:
        logger.warning("series_sort_failed slide_id=%s", slide.id, exc_info=True)
        return None

    if decision.existing_index is not None:
        series = shown[decision.existing_index]
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
