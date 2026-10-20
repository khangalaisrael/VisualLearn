"""POST /feedback: a 👍 or 👎 on one answer, with an optional comment.

The answer is a slide's summary or an assistant reply in a chat. Signed-out
students can rate too: their feedback is kept with no account. Who may rate
an answer follows `ensure_presentation_access`, the same rule as reading it:
an owned capture or chat only by its owner, an anonymous one by anyone. The
rated text is copied from the database, never taken from the request, so
the admin page shows what the student actually saw.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    enforce_feedback_rate_limit,
    ensure_presentation_access,
    get_current_user_id,
    verify_api_key,
)
from app.db.session import get_db
from app.models.orm import Conversation, Feedback, Message, Presentation, Slide
from app.models.schemas import FeedbackCreateRequest, FeedbackOut

router = APIRouter(tags=["feedback"], dependencies=[Depends(verify_api_key)])

# Enough of a long answer to see what went wrong without keeping all of it.
EXCERPT_CHARS = 4000


def _parse(value: str | None, detail: str) -> uuid.UUID:
    try:
        return uuid.UUID(value or "")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=detail) from exc


async def _check_presentation(db: AsyncSession, presentation_id: uuid.UUID | None, user_id: uuid.UUID | None) -> None:
    presentation = await db.get(Presentation, presentation_id) if presentation_id is not None else None
    if presentation is not None:
        ensure_presentation_access(presentation, user_id)


async def _rated_text(db: AsyncSession, body: FeedbackCreateRequest, user_id: uuid.UUID | None) -> tuple[uuid.UUID, str]:
    """The id of the rated answer and its text, or 404 when it is unknown or
    belongs to someone else."""
    if body.target == "summary":
        slide = await db.get(Slide, _parse(body.slide_id, "Unknown slide"))
        if slide is None:
            raise HTTPException(status_code=404, detail="Unknown slide")
        await _check_presentation(db, slide.presentation_id, user_id)
        return slide.id, slide.summary or ""

    message = await db.get(Message, _parse(body.message_id, "Unknown message"))
    conversation = await db.get(Conversation, message.conversation_id) if message is not None else None
    if message is None or conversation is None or message.role != "assistant":
        raise HTTPException(status_code=404, detail="Unknown message")
    if conversation.user_id is not None and conversation.user_id != user_id:
        raise HTTPException(status_code=404, detail="Unknown message")
    await _check_presentation(db, conversation.presentation_id, user_id)
    return message.id, message.content


async def _earlier(
    db: AsyncSession, body: FeedbackCreateRequest, user_id: uuid.UUID | None, answer_id: uuid.UUID
) -> Feedback | None:
    """This student's earlier rating of the same answer, if any. A signed-in
    student's is looked up; a signed-out one's only by the id it came back with."""
    column = Feedback.slide_id if body.target == "summary" else Feedback.message_id
    if body.feedback_id:
        try:
            earlier = await db.get(Feedback, uuid.UUID(body.feedback_id))
        except ValueError:
            earlier = None
        if earlier is not None and earlier.user_id == user_id and getattr(earlier, column.key) == answer_id:
            return earlier
    if user_id is None:
        return None
    result = await db.execute(
        select(Feedback).where(Feedback.user_id == user_id, Feedback.target == body.target, column == answer_id)
    )
    return result.scalars().first()


@router.post("/feedback", response_model=FeedbackOut, dependencies=[Depends(enforce_feedback_rate_limit)])
async def give_feedback(
    body: FeedbackCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user_id: uuid.UUID | None = Depends(get_current_user_id),
) -> FeedbackOut:
    answer_id, text = await _rated_text(db, body, current_user_id)
    comment = (body.comment or "").strip() or None

    feedback = await _earlier(db, body, current_user_id, answer_id)
    if feedback is None:
        feedback = Feedback(
            user_id=current_user_id,
            target=body.target,
            slide_id=answer_id if body.target == "summary" else None,
            message_id=answer_id if body.target == "chat" else None,
            rating=body.rating,
            comment=comment,
            answer_excerpt=text[:EXCERPT_CHARS],
        )
        db.add(feedback)
    else:
        feedback.rating = body.rating
        feedback.comment = comment
        feedback.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(feedback)
    return FeedbackOut(id=str(feedback.id), rating="up" if feedback.rating == "up" else "down")
