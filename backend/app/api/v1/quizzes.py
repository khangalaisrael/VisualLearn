"""Quizzes on a series: generate one from its slides, list them, take them.

POST /series/{id}/quizzes writes a new quiz (one model call, counted against
a daily allowance); GET lists a series' quizzes with the best score so far;
POST /quizzes/{id}/attempts records a finished run. Marking is a comparison
against the stored correct option, never a model call. Tutoring on a missed
question goes through POST /chat in "tutor" mode (api/v1/chat.py).
"""

import asyncio
import logging
import uuid
from collections.abc import Sequence

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    enforce_quiz_rate_limit,
    get_current_user,
    get_current_user_id,
    get_quiz_generator,
    get_resource_finder,
    is_admin,
    verify_api_key,
)
from app.core.config import get_settings
from app.db.session import get_db
from app.models.orm import Quiz, QuizAttempt, Series, User
from app.models.schemas import (
    QuizAttemptRequest,
    QuizAttemptResponse,
    QuizCreateRequest,
    QuizListResponse,
    QuizOut,
    QuizQuestion,
    QuizResource,
    QuizSummary,
)
from app.repositories.usage_events import UsageEventRepository
from app.services.quiz_generator import QuizGenerator
from app.services.resource_finder import ResearchResult, ResourceFinder
from app.services.retention import retention_cutoff
from app.services.series_source import read_series
from app.services.usage import estimate_cost_usd, start_accumulator

logger = logging.getLogger(__name__)

router = APIRouter(tags=["quizzes"], dependencies=[Depends(verify_api_key)])


def _require_user(current_user_id: uuid.UUID | None) -> uuid.UUID:
    if current_user_id is None:
        raise HTTPException(status_code=401, detail="Sign in to make and take quizzes.")
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


async def _owned_quiz(db: AsyncSession, quiz_id: str, user_id: uuid.UUID) -> Quiz:
    quiz = await db.get(Quiz, _parse(quiz_id, "Unknown quiz"))
    if quiz is None or quiz.user_id != user_id:
        raise HTTPException(status_code=404, detail="Unknown quiz")
    return quiz


async def _research(finder: ResourceFinder, series: Series, subtopics: list[str]) -> ResearchResult:
    """Never raises and never outlasts its time limit: a quiz without
    resources is still a quiz."""
    try:
        return await asyncio.wait_for(
            finder.find(category=series.category, title=series.title, subtopics=subtopics[:8]),
            timeout=get_settings().research_timeout_seconds,
        )
    except Exception:
        logger.warning("quiz_research_failed series_id=%s", series.id, exc_info=True)
        return ResearchResult()


async def _attempt_stats(db: AsyncSession, quiz_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, tuple[int, int]]:
    """quiz id -> (number of attempts, best score)."""
    if not quiz_ids:
        return {}
    rows = await db.execute(
        select(QuizAttempt.quiz_id, func.count(QuizAttempt.id), func.max(QuizAttempt.score))
        .where(QuizAttempt.quiz_id.in_(quiz_ids))
        .group_by(QuizAttempt.quiz_id)
    )
    return {quiz_id: (count, best) for quiz_id, count, best in rows.all()}


def _summary(quiz: Quiz, stats: dict[uuid.UUID, tuple[int, int]]) -> dict:
    attempts, best = stats.get(quiz.id, (0, None))
    return {
        "id": str(quiz.id),
        "title": quiz.title,
        "question_count": len(quiz.questions),
        "created_at": quiz.created_at,
        "attempts": attempts,
        "best_score": best,
    }


def _out(quiz: Quiz, stats: dict[uuid.UUID, tuple[int, int]]) -> QuizOut:
    return QuizOut(
        **_summary(quiz, stats),
        series_id=str(quiz.series_id),
        questions=[QuizQuestion(**question) for question in quiz.questions],
        resources=[QuizResource(**resource) for resource in quiz.resources or []],
    )


@router.post(
    "/series/{series_id}/quizzes",
    response_model=QuizOut,
    status_code=201,
    dependencies=[Depends(enforce_quiz_rate_limit)],
)
async def create_quiz(
    series_id: str,
    body: QuizCreateRequest,
    db: AsyncSession = Depends(get_db),
    generator: QuizGenerator = Depends(get_quiz_generator),
    finder: ResourceFinder | None = Depends(get_resource_finder),
    user: User | None = Depends(get_current_user),
) -> QuizOut:
    user_id = _require_user(user.id if user else None)
    series = await _owned_series(db, series_id, user_id)
    if body.research and not is_admin(user):
        raise HTTPException(status_code=403, detail="Web research for quizzes is not open to everyone yet.")

    source = await read_series(db, series)
    if source is None:
        raise HTTPException(status_code=422, detail="This series has no slides to write a quiz from.")

    usage = start_accumulator()
    # The questions and the web research do not depend on each other, so they run side by side.
    research_task = (
        asyncio.create_task(_research(finder, series, source.subtopics)) if body.research and finder is not None else None
    )
    try:
        generated = await generator.generate(source.text, body.count)
    except Exception as exc:
        if research_task is not None:
            research_task.cancel()
        raise HTTPException(status_code=502, detail="The quiz could not be written. Please try again.") from exc
    research = await research_task if research_task is not None else None

    quiz = Quiz(
        user_id=user_id,
        series_id=series.id,
        title=generated.title,
        questions=[
            {
                "question": q.question,
                "options": q.options,
                "correct_index": q.correct_index,
                "explanation": q.explanation,
                "slide_id": str(source.slide_ids[q.source_index]) if q.source_index is not None else None,
            }
            for q in generated.questions
        ],
        resources=[{"title": r.title, "url": r.url, "why": r.why} for r in research.resources] if research else [],
    )
    db.add(quiz)
    await UsageEventRepository(db).record(
        user_id=user_id,
        action="quiz",
        model=generator.model_name,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        est_cost_usd=estimate_cost_usd(generator.model_name, usage.input_tokens, usage.output_tokens),
    )
    if research is not None and finder is not None:
        await UsageEventRepository(db).record(
            user_id=user_id,
            action="research",
            model=finder.model_name,
            input_tokens=research.input_tokens,
            output_tokens=research.output_tokens,
            est_cost_usd=estimate_cost_usd(finder.model_name, research.input_tokens, research.output_tokens)
            + research.searches * get_settings().web_search_usd_per_request,
        )
    await db.commit()
    await db.refresh(quiz)
    return _out(quiz, {})


@router.get("/series/{series_id}/quizzes", response_model=QuizListResponse)
async def list_quizzes(
    series_id: str,
    db: AsyncSession = Depends(get_db),
    current_user_id: uuid.UUID | None = Depends(get_current_user_id),
) -> QuizListResponse:
    user_id = _require_user(current_user_id)
    series = await _owned_series(db, series_id, user_id)
    quizzes = list(
        (
            await db.execute(
                select(Quiz)
                .where(Quiz.user_id == user_id, Quiz.series_id == series.id, Quiz.created_at >= retention_cutoff())
                .order_by(Quiz.created_at.desc())
            )
        ).scalars()
    )
    stats = await _attempt_stats(db, [quiz.id for quiz in quizzes])
    return QuizListResponse(quizzes=[QuizSummary(**_summary(quiz, stats)) for quiz in quizzes])


@router.get("/quizzes/{quiz_id}", response_model=QuizOut)
async def get_quiz(
    quiz_id: str,
    db: AsyncSession = Depends(get_db),
    current_user_id: uuid.UUID | None = Depends(get_current_user_id),
) -> QuizOut:
    quiz = await _owned_quiz(db, quiz_id, _require_user(current_user_id))
    return _out(quiz, await _attempt_stats(db, [quiz.id]))


@router.post("/quizzes/{quiz_id}/attempts", response_model=QuizAttemptResponse)
async def record_attempt(
    quiz_id: str,
    body: QuizAttemptRequest,
    db: AsyncSession = Depends(get_db),
    current_user_id: uuid.UUID | None = Depends(get_current_user_id),
) -> QuizAttemptResponse:
    quiz = await _owned_quiz(db, quiz_id, _require_user(current_user_id))
    if len(body.answers) != len(quiz.questions):
        raise HTTPException(status_code=422, detail="One answer per question is required (null for a skipped one)")
    score = sum(
        1 for answer, question in zip(body.answers, quiz.questions) if answer is not None and answer == question["correct_index"]
    )
    db.add(QuizAttempt(quiz_id=quiz.id, answers=body.answers, score=score))
    await db.commit()
    return QuizAttemptResponse(score=score, total=len(quiz.questions))


@router.delete("/quizzes/{quiz_id}", status_code=204)
async def delete_quiz(
    quiz_id: str,
    db: AsyncSession = Depends(get_db),
    current_user_id: uuid.UUID | None = Depends(get_current_user_id),
) -> None:
    quiz = await _owned_quiz(db, quiz_id, _require_user(current_user_id))
    await db.execute(delete(QuizAttempt).where(QuizAttempt.quiz_id == quiz.id))
    await db.execute(delete(Quiz).where(Quiz.id == quiz.id))
    await db.commit()
