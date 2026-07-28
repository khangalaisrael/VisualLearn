"""Repository for the `presentations` table (docs/DATA_MODEL.md §3)."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orm import Presentation


class PresentationRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get(self, presentation_id: uuid.UUID) -> Presentation | None:
        return await self._db.get(Presentation, presentation_id)

    async def create(self, *, title: str, source_type: str) -> Presentation:
        presentation = Presentation(title=title, source_type=source_type)
        self._db.add(presentation)
        await self._db.flush()
        return presentation
