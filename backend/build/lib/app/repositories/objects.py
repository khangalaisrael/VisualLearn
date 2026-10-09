"""Repository for the `objects` table (docs/DATA_MODEL.md §3) — persisted
once per slide, at slide-creation time (see api/v1/slides.py), so a later
Figure/Slide-mode chat request can resolve `object_id`/`slide_id` to real
content instead of only the ephemeral analyze-response JSON.

Object ids are freshly minted here (`create_many` ignores whatever `id`
each `SlideObject` already carries), not reused from the analysis cache.
The image-hash cache (CacheService) is global — the same screenshot bytes
reappearing under a *different* presentation is a cache hit there, and
round-trips the same cached ids — but each presentation's Slide row still
needs its own objects with ids unique across the whole table (the primary
key). Minting fresh ids per slide, and treating this table (not the cache)
as the source of truth for "what object ids exist for this slide" once a
Slide row exists, keeps both caches free to do their own thing without
colliding: the image-hash cache saves the model call; this table is what
`api/v1/chat.py`'s `object_id`/`slide_id` lookups actually resolve against.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orm import ObjectRecord
from app.models.schemas import BoundingBox, GraphStructure, SlideObject


class ObjectRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create_many(self, slide_id: uuid.UUID, objects: list[SlideObject]) -> list[ObjectRecord]:
        """Bulk-inserts one row per object with a freshly generated id —
        see this module's docstring for why the caller's `SlideObject.id`
        is intentionally not reused."""
        records = [
            ObjectRecord(
                id=uuid.uuid4(),
                slide_id=slide_id,
                type=obj.type,
                bounding_box=obj.bounding_box.model_dump(mode="json"),
                extracted_text=obj.extracted_text,
                latex=obj.latex,
                language=obj.language,
                summary=obj.summary,
                confidence=obj.confidence,
                graph_structure=obj.graph_structure.model_dump(mode="json") if obj.graph_structure else None,
            )
            for obj in objects
        ]
        self._db.add_all(records)
        await self._db.flush()
        return records

    @staticmethod
    def to_slide_object(record: ObjectRecord) -> SlideObject:
        """Converts a persisted row back to the API/cache schema — used to
        build the response when a slide already exists (so the ids
        returned to the client always match this table, whichever path —
        fresh analysis or an existing slide — served the request)."""
        return SlideObject(
            id=str(record.id),
            type=record.type,
            bounding_box=BoundingBox(**record.bounding_box),
            extracted_text=record.extracted_text,
            latex=record.latex,
            language=record.language,
            summary=record.summary,
            confidence=record.confidence,
            graph_structure=GraphStructure(**record.graph_structure) if record.graph_structure else None,
        )

    async def get(self, object_id: uuid.UUID) -> ObjectRecord | None:
        result = await self._db.execute(select(ObjectRecord).where(ObjectRecord.id == object_id))
        return result.scalar_one_or_none()

    async def list_by_slide(self, slide_id: uuid.UUID) -> list[ObjectRecord]:
        """Ordered by reading position (top-to-bottom, then left-to-right)
        — an approximation, since no explicit reading-order field exists
        yet; good enough for assembling Slide-mode chat context.

        Sorted in Python rather than via a DB-side JSON-path ORDER BY:
        `bounding_box` is a plain JSON blob (not typed columns), and the
        test suite runs against SQLite (docs/DATA_MODEL.md's JSONB
        indexing is Postgres-only) — sorting the small per-slide result
        set in Python works identically on both."""
        result = await self._db.execute(select(ObjectRecord).where(ObjectRecord.slide_id == slide_id))
        records = list(result.scalars().all())
        records.sort(key=lambda r: (r.bounding_box["y"], r.bounding_box["x"]))
        return records
