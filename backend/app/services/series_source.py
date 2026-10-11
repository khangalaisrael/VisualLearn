"""A series read as text, for the things written from it (quizzes, study aids).

Slides are sent to a model as their already-extracted text, never as images,
each cut to a fixed length. The whole series is read, however long: a quiz
or a guide that only knew the latest slides would leave the rest of a long
series unpractised.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orm import ObjectRecord, Series, Slide
from app.repositories.objects import ObjectRepository
from app.services.retention import retention_cutoff

MAX_PRACTICE_SLIDES = 3
MAX_SLIDE_CHARS = 1200


@dataclass(frozen=True)
class SeriesText:
    """`slides` and `practice` are slide texts. A position in `slides`
    (counted from 1) is how a model refers to a slide."""

    category: str
    title: str
    slides: list[str]
    practice: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SeriesSource:
    text: SeriesText
    # The id of the slide behind each entry of `text.slides`, in the same order.
    slide_ids: list[uuid.UUID]
    # Subtopics of those slides, without repeats, in capture order.
    subtopics: list[str]


def slide_text(slide: Slide, objects: Sequence[ObjectRecord]) -> str:
    heading = f"[{slide.subtopic}] " if slide.subtopic else ""
    body = "\n".join(o.extracted_text or o.latex or o.summary or "" for o in objects).strip()
    return f"{heading}{slide.summary or ''}\n{body}"[:MAX_SLIDE_CHARS].strip()


async def read_series(db: AsyncSession, series: Series) -> SeriesSource | None:
    """None when the series has no unexpired slides to read."""
    slides = list(
        (
            await db.execute(
                select(Slide)
                .where(Slide.series_id == series.id, Slide.created_at >= retention_cutoff())
                .order_by(Slide.created_at.desc())
            )
        ).scalars()
    )
    practice = [s for s in slides if s.content_kind == "practice"][:MAX_PRACTICE_SLIDES]
    # Written from the lecture slides; a series of nothing but practice
    # slides is read from those instead.
    lectures = [s for s in slides if s.content_kind != "practice"] or practice
    lectures = lectures[::-1]  # in the order they were captured
    if not lectures:
        return None

    objects = ObjectRepository(db)
    return SeriesSource(
        text=SeriesText(
            category=series.category,
            title=series.title,
            slides=[slide_text(s, await objects.list_by_slide(s.id)) for s in lectures],
            practice=[slide_text(s, await objects.list_by_slide(s.id)) for s in practice if s not in lectures],
        ),
        slide_ids=[s.id for s in lectures],
        subtopics=list(dict.fromkeys(s.subtopic for s in lectures if s.subtopic)),
    )


def format_slides(text: SeriesText) -> str:
    """The numbered slides (and any practice questions) as one prompt block."""
    slides = "\n\n".join(f"[Slide {i}]\n{body}" for i, body in enumerate(text.slides, start=1))
    practice = (
        "\n\n<practice_questions_from_the_course>\n" + "\n\n".join(text.practice) + "\n</practice_questions_from_the_course>"
        if text.practice
        else ""
    )
    return f"Series: {text.title} ({text.category})\n\n<slides>\n{slides}\n</slides>{practice}"
