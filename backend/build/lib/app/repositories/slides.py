"""Repository for the `slides` table (docs/DATA_MODEL.md §3).

`get_by_hash` backs the de-duplication behavior described there: a slide
re-shown within the same presentation resolves to its existing row instead
of inserting a duplicate.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orm import Slide


class SlideRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get(self, slide_id: uuid.UUID) -> Slide | None:
        return await self._db.get(Slide, slide_id)

    async def get_by_hash(self, presentation_id: uuid.UUID, image_hash: str) -> Slide | None:
        result = await self._db.execute(
            select(Slide).where(
                Slide.presentation_id == presentation_id,
                Slide.image_hash == image_hash,
            )
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        presentation_id: uuid.UUID,
        slide_number: int,
        image_hash: str,
        status: str,
        summary: str | None,
    ) -> Slide:
        slide = Slide(
            presentation_id=presentation_id,
            slide_number=slide_number,
            image_hash=image_hash,
            status=status,
            summary=summary,
            analyzed_at=datetime.now(UTC) if status == "analyzed" else None,
        )
        self._db.add(slide)
        await self._db.flush()
        return slide
