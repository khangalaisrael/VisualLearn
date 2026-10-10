"""Capture history: the signed-in user's lectures and the captures in them.

GET /lectures lists them (text only; thumbnails never reach the server).
GET /slides/{id} re-opens one capture; the DELETEs remove a capture or a
whole lecture together with its chats. Reads are by owner; deletes need a
session token, since an anonymous capture has no owner to authorise.
"""

import uuid
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ensure_presentation_access, get_current_user_id, verify_api_key
from app.core.config import get_settings
from app.db.session import get_db
from app.models.orm import Conversation, Message, Presentation, Slide
from app.models.schemas import (
    CaptureConversation,
    CaptureSummary,
    LectureListResponse,
    LectureSummary,
    SlideAnalysisResponse,
)
from app.repositories.objects import ObjectRepository
from app.repositories.presentations import PresentationRepository
from app.repositories.slides import SlideRepository
from app.services.presentations import delete_presentation, delete_slides
from app.services.retention import retention_cutoff

router = APIRouter(tags=["lectures"], dependencies=[Depends(verify_api_key)])

_SUMMARY_PREVIEW_CHARS = 400


def _require_user(current_user_id: uuid.UUID | None) -> uuid.UUID:
    if current_user_id is None:
        raise HTTPException(status_code=401, detail="Sign in to see your recent captures.")
    return current_user_id


def _parse(value: str, detail: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=detail) from exc


@router.get("/lectures", response_model=LectureListResponse)
async def list_lectures(
    db: AsyncSession = Depends(get_db),
    current_user_id: uuid.UUID | None = Depends(get_current_user_id),
) -> LectureListResponse:
    user_id = _require_user(current_user_id)
    since = retention_cutoff()

    rows = (
        await db.execute(
            select(Slide, Presentation)
            .join(Presentation, Presentation.id == Slide.presentation_id)
            .where(Presentation.user_id == user_id, Slide.created_at >= since)
            .order_by(Slide.created_at.desc())
        )
    ).all()

    slide_ids = [slide.id for slide, _ in rows]
    chats: dict[uuid.UUID, list[CaptureConversation]] = defaultdict(list)
    if slide_ids:
        chat_rows = (
            await db.execute(
                select(
                    Conversation.id,
                    Conversation.title,
                    Conversation.slide_id,
                    Conversation.last_activity_at,
                    func.count(Message.id),
                )
                .join(Message, Message.conversation_id == Conversation.id)
                .where(
                    Conversation.user_id == user_id,
                    Conversation.slide_id.in_(slide_ids),
                    Conversation.last_activity_at >= since,
                )
                .group_by(Conversation.id)
                .order_by(Conversation.last_activity_at.desc())
            )
        ).all()
        for conversation_id, title, slide_id, last_activity_at, message_count in chat_rows:
            chats[slide_id].append(
                CaptureConversation(
                    id=str(conversation_id),
                    title=title or "Untitled chat",
                    message_count=message_count,
                    last_activity_at=last_activity_at,
                )
            )

    lectures: dict[uuid.UUID, LectureSummary] = {}
    for slide, presentation in rows:
        lecture = lectures.get(presentation.id)
        if lecture is None:
            lecture = lectures[presentation.id] = LectureSummary(
                id=str(presentation.id),
                title=presentation.title,
                page_url=presentation.page_url,
                last_activity_at=slide.created_at,
                captures=[],
            )
        lecture.captures.append(
            CaptureSummary(
                slide_id=str(slide.id),
                slide_number=slide.slide_number,
                summary=(slide.summary or "")[:_SUMMARY_PREVIEW_CHARS],
                created_at=slide.created_at,
                conversations=chats.get(slide.id, []),
            )
        )
        # Chat activity counts toward when the lecture was last touched.
        for chat in chats.get(slide.id, []):
            if chat.last_activity_at > lecture.last_activity_at:
                lecture.last_activity_at = chat.last_activity_at

    ordered = sorted(lectures.values(), key=lambda lecture: lecture.last_activity_at, reverse=True)
    return LectureListResponse(retention_days=get_settings().chat_retention_days, lectures=ordered)


async def _get_slide(db: AsyncSession, slide_id: str, current_user_id: uuid.UUID | None) -> Slide:
    slide = await SlideRepository(db).get(_parse(slide_id, "Unknown slide"))
    if slide is None:
        raise HTTPException(status_code=404, detail="Unknown slide")
    presentation = await PresentationRepository(db).get(slide.presentation_id)
    if presentation is None:
        raise HTTPException(status_code=404, detail="Unknown slide")
    ensure_presentation_access(presentation, current_user_id)
    return slide


@router.get("/slides/{slide_id}", response_model=SlideAnalysisResponse)
async def get_slide(
    slide_id: str,
    db: AsyncSession = Depends(get_db),
    current_user_id: uuid.UUID | None = Depends(get_current_user_id),
) -> SlideAnalysisResponse:
    slide = await _get_slide(db, slide_id, current_user_id)
    objects = ObjectRepository(db)
    return SlideAnalysisResponse(
        presentation_id=slide.presentation_id,
        slide_id=slide.id,
        cache_hit=True,
        status=slide.status,
        objects=[objects.to_slide_object(record) for record in await objects.list_by_slide(slide.id)],
        summary=slide.summary or "",
    )


@router.delete("/slides/{slide_id}", status_code=204)
async def delete_slide(
    slide_id: str,
    db: AsyncSession = Depends(get_db),
    current_user_id: uuid.UUID | None = Depends(get_current_user_id),
) -> None:
    user_id = _require_user(current_user_id)
    slide = await _get_slide(db, slide_id, user_id)
    presentation = await PresentationRepository(db).get(slide.presentation_id)
    if presentation is None or presentation.user_id != user_id:
        raise HTTPException(status_code=404, detail="Unknown slide")
    await delete_slides(db, [slide.id])
    await db.commit()


@router.delete("/lectures/{presentation_id}", status_code=204)
async def delete_lecture(
    presentation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user_id: uuid.UUID | None = Depends(get_current_user_id),
) -> None:
    user_id = _require_user(current_user_id)
    presentation = await PresentationRepository(db).get(_parse(presentation_id, "Unknown lecture"))
    if presentation is None or presentation.user_id != user_id:
        raise HTTPException(status_code=404, detail="Unknown lecture")
    await delete_presentation(db, presentation.id)
    await db.commit()
