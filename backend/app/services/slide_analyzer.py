"""SlideAnalyzer protocol and the placeholder (no-API-key) implementation.

Per docs/adr/ADR-004-vlm-first-pipeline.md, every analysis backend
implements this protocol so the real Claude vision pipeline
(`ClaudeVLMAnalyzer`, app/services/claude_vlm_analyzer.py) can be swapped in
without any caller-side change — no router, repository, or test depends on
the concrete implementation, only on `SlideAnalyzer`.
"""

import uuid
from dataclasses import dataclass
from typing import Protocol

from app.models.schemas import BoundingBox, SlideObject


@dataclass(frozen=True)
class AnalysisResult:
    objects: list[SlideObject]
    summary: str


class SlideAnalyzer(Protocol):
    """Produces structured objects (layout, text, LaTeX, figure summaries) for a slide image."""

    # Recorded in cache_entries.model_used (see services/cache_service.py)
    # and in logs (see api/v1/slides.py) — every implementation must expose
    # a stable, human-readable identifier.
    model_name: str

    async def analyze(self, image_bytes: bytes) -> AnalysisResult: ...


class PlaceholderSlideAnalyzer:
    """Stand-in used when no ANTHROPIC_API_KEY is configured (see
    app/api/deps.py) and by the test suite (tests/backend/conftest.py, which
    overrides the analyzer dependency to guarantee tests never call the real
    Claude API). Returns a fixed placeholder object, no model call.
    """

    model_name = "placeholder"

    async def analyze(self, image_bytes: bytes) -> AnalysisResult:
        del image_bytes  # unused — no model call is made
        placeholder_object = SlideObject(
            id=str(uuid.uuid4()),
            type="paragraph",
            bounding_box=BoundingBox(x=0.05, y=0.05, width=0.9, height=0.2),
            extracted_text="Slide analysis is not configured (no ANTHROPIC_API_KEY set).",
            latex=None,
            summary="Placeholder analysis result — set ANTHROPIC_API_KEY to enable real analysis.",
            confidence=0.0,
        )
        return AnalysisResult(
            objects=[placeholder_object],
            summary="Placeholder summary — set ANTHROPIC_API_KEY to enable real analysis (see ADR-004).",
        )
