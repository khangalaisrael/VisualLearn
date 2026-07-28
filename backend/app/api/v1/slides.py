"""POST /slides/analyze — docs/API_CONTRACT.md §2.

Milestone 2 (docs/ROADMAP.md): the analyzer is real (ClaudeVLMAnalyzer, when
ANTHROPIC_API_KEY is set — see app/api/deps.py) and results are cached by
image hash across presentations (app/services/cache_service.py).

Deviation from the original API_CONTRACT.md draft: the request no longer
accepts a client-supplied `image_hash`. The backend derives it from the
uploaded bytes instead — see the docstring on `analyze_slide` below for why.

Milestone 2 also refines `cache_hit`'s meaning: it now reflects whether the
*analysis* was served from the cache (a global, hash-keyed lookup —
services/cache_service.py), not whether a Slide row already existed in this
presentation (a separate, presentation-scoped de-duplication concern
handled by repositories/slides.py). The two can differ: the same slide
image reappearing in a different presentation is a cache hit but not an
existing Slide row.
"""

import hashlib
import logging
import time
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_slide_analyzer, verify_api_key
from app.core.cache import get_redis
from app.core.config import get_settings
from app.db.session import get_db
from app.models.schemas import SlideAnalysisResponse
from app.repositories.objects import ObjectRepository
from app.repositories.presentations import PresentationRepository
from app.repositories.slides import SlideRepository
from app.services.cache_service import CacheService
from app.services.slide_analyzer import SlideAnalyzer

logger = logging.getLogger(__name__)

router = APIRouter(tags=["slides"], dependencies=[Depends(verify_api_key)])


@router.post("/slides/analyze", response_model=SlideAnalysisResponse)
async def analyze_slide(
    image: UploadFile = File(...),
    presentation_id: str | None = Form(default=None),
    slide_number: int = Form(...),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    analyzer: SlideAnalyzer = Depends(get_slide_analyzer),
) -> SlideAnalysisResponse:
    """Analyze a captured slide image.

    The image hash used for de-duplication and caching is computed here
    from the bytes actually received, not trusted from the client. A
    client-supplied hash that didn't match its bytes would silently poison
    the analysis cache — recomputing costs one cheap SHA-256 pass over
    bytes already in memory and removes that trust boundary entirely.
    """
    settings = get_settings()
    image_bytes = await image.read()

    # 422/413 are used as plain integers rather than
    # status.HTTP_422_UNPROCESSABLE_ENTITY / status.HTTP_413_REQUEST_ENTITY_TOO_LARGE:
    # both symbolic names are deprecated aliases as of the currently pinned
    # Starlette, and their replacement names aren't guaranteed to exist on
    # every version satisfying this project's `fastapi>=0.115,<1.0` pin.
    if not image_bytes:
        raise HTTPException(status_code=422, detail="Empty image upload")
    if len(image_bytes) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="Image exceeds maximum upload size")

    image_hash = hashlib.sha256(image_bytes).hexdigest()

    presentations = PresentationRepository(db)
    slides = SlideRepository(db)
    cache = CacheService(redis, db)

    # Falsy check, not `is not None`: an untouched optional field in
    # Swagger UI's "Try it out" form (and some other multipart clients)
    # submits an empty string rather than omitting the field entirely, and
    # "" should mean the same thing as "not provided", not fail UUID parsing.
    if presentation_id:
        try:
            presentation_uuid = uuid.UUID(presentation_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Malformed presentation_id") from exc
        presentation = await presentations.get(presentation_uuid)
        if presentation is None:
            raise HTTPException(status_code=404, detail="Unknown presentation_id")
    else:
        presentation = await presentations.create(title="Untitled presentation", source_type="live_capture")

    start = time.perf_counter()
    cached_result = await cache.get(image_hash)
    if cached_result is not None:
        result = cached_result
        cache_hit = True
    else:
        result = await analyzer.analyze(image_bytes)
        await cache.set(image_hash, result, model_used=analyzer.model_name)
        cache_hit = False
    elapsed_ms = int((time.perf_counter() - start) * 1000)

    objects_repo = ObjectRepository(db)
    existing_slide = await slides.get_by_hash(presentation.id, image_hash)
    if existing_slide is not None:
        # This exact image was already analyzed for this presentation —
        # its objects (and their ids) already exist from that first time.
        # Returned from the objects table, not `result.objects`: the
        # latter comes from the image-hash cache, which is shared across
        # presentations and round-trips whatever ids were cached under a
        # *different* presentation's slide — see ObjectRepository's
        # docstring for why object identity belongs to this table, not
        # the cache.
        slide = existing_slide
        response_objects = [objects_repo.to_slide_object(record) for record in await objects_repo.list_by_slide(slide.id)]
    else:
        slide = await slides.create(
            presentation_id=presentation.id,
            slide_number=slide_number,
            image_hash=image_hash,
            status="analyzed",
            summary=result.summary,
        )
        # Fresh ids minted here (see ObjectRepository.create_many) since
        # this is the first time this specific slide gets objects, even
        # if `result` itself came from another presentation's cache hit.
        created = await objects_repo.create_many(slide.id, result.objects)
        response_objects = [objects_repo.to_slide_object(record) for record in created]

    await db.commit()

    # Structured per docs/ARCHITECTURE.md §6: processing time, model used,
    # cache hit/miss, object count — never the extracted slide content
    # itself (extracted_text, latex, summary are deliberately omitted).
    logger.info(
        "slide_analysis_complete cache_hit=%s model_used=%s object_count=%d elapsed_ms=%d",
        cache_hit,
        analyzer.model_name,
        len(response_objects),
        elapsed_ms,
    )

    return SlideAnalysisResponse(
        presentation_id=presentation.id,
        slide_id=slide.id,
        cache_hit=cache_hit,
        status=slide.status,
        objects=response_objects,
        summary=result.summary,
    )
