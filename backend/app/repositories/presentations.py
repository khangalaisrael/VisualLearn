"""Repository for the `presentations` table (docs/DATA_MODEL.md §3)."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orm import Presentation


class PresentationRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get(self, presentation_id: uuid.UUID) -> Presentation | None:
        return await self._db.get(Presentation, presentation_id)

    async def create(
        self,
        *,
        title: str,
        source_type: str,
        user_id: uuid.UUID | None = None,
        page_url: str | None = None,
        lecture_key: str | None = None,
    ) -> Presentation:
        # `user_id=None` (the default) is the unchanged local-first/
        # anonymous flow (docs/PublicHostingMVP.md Phase 3) — a presentation
        # only gets attributed to an account when the request that created
        # it carried a valid session token.
        presentation = Presentation(
            title=title, source_type=source_type, user_id=user_id, page_url=page_url, lecture_key=lecture_key
        )
        self._db.add(presentation)
        await self._db.flush()
        return presentation

    async def get_for_lecture(self, user_id: uuid.UUID, lecture_key: str) -> Presentation | None:
        """The signed-in user's most recent presentation for this lecture, so
        a second device (or a cleared browser) keeps adding to the same group."""
        result = await self._db.execute(
            select(Presentation)
            .where(Presentation.user_id == user_id, Presentation.lecture_key == lecture_key)
            .order_by(Presentation.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
