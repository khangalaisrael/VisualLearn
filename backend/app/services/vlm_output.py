"""Shared response schema and parsing logic for VLM-based SlideAnalyzer
implementations (docs/adr/ADR-004-vlm-first-pipeline.md).

Both ClaudeVLMAnalyzer and OpenAIVLMAnalyzer (docs/adr/ADR-009) send the
same prompt (prompts/analysis.v3.md) and request the same JSON-schema
output shape from their respective provider's structured-outputs feature —
only the request/response plumbing differs per provider. Factored out here
so that shape and its parsing rules are defined exactly once.

Also builds `graph_structure` for graph-shaped diagrams (docs/adr/ADR-010),
via a hybrid, two-pass pipeline. Pass 1 (the main analysis call above) only
tells us "this object looks like a node/edge graph" — its own graph_nodes/
graph_weight_labels guesses are discarded, not used for positions. Live
testing found the VLM's position accuracy degrades badly when a small
diagram has to be localized within an entire busy slide (errors bad enough
to land outside the diagram entirely — see graph_topology.py's
crop_object_region docstring). Pass 2 crops the image down to just that
object's region and sends a second, focused call (`locate_graph_fn`,
implemented per-provider) asking only for node/weight-label positions
within that small, upscaled crop — a much easier localization task. Only
then does app/services/graph_topology.py's classical CV determine actual
edge connectivity; neither VLM pass is ever asked to do that.
"""

import logging
import uuid
from collections.abc import Awaitable, Callable

from app.models.schemas import BoundingBox, GraphStructure, SlideObject
from app.services.graph_topology import RawGraphNode, RawWeightLabel, build_graph_structure, crop_object_region
from app.services.slide_analyzer import AnalysisResult

logger = logging.getLogger(__name__)

# The second-pass call (docs/adr/ADR-010's two-pass follow-up): given a
# crop of just one graph object, return its node/weight-label positions
# relative to that crop (prompts/graph_localization.v1.md gives the exact
# contract). Implemented per-provider (OpenAIVLMAnalyzer/ClaudeVLMAnalyzer),
# each with its own client and this same schema.
GRAPH_LOCALIZATION_SCHEMA = {
    "type": "object",
    "properties": {
        "graph_nodes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "x": {"type": "number"},
                    "y": {"type": "number"},
                    "radius": {"type": "number"},
                },
                "required": ["label", "x", "y", "radius"],
                "additionalProperties": False,
            },
        },
        "graph_weight_labels": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "value": {"type": "number"},
                    "x": {"type": "number"},
                    "y": {"type": "number"},
                },
                "required": ["value", "x", "y"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["graph_nodes", "graph_weight_labels"],
    "additionalProperties": False,
}

LocateGraphFn = Callable[[bytes], Awaitable[dict]]

# docs/PROMPTS.md §1 "Structured outputs over prefill" + the JSON Schema
# Limitations it notes: numeric constraints (minimum/maximum) aren't
# reliably supported across providers' structured-output subsets, so
# `confidence` is unconstrained here and clamped in Python after parsing
# (see clamp_confidence). `id` is deliberately NOT requested from the model
# — assigning stable unique identifiers is a server-side concern, not
# something to trust a vision model's judgment on; ids are generated in
# to_slide_object instead.
#
# `graph_nodes` / `graph_weight_labels` (docs/adr/ADR-010): populated by
# the model only for graph-shaped diagrams (node/edge structures), null
# otherwise. Used here only as a trigger signal ("this object is a graph,
# go run the second localization pass") — the actual positions from this
# first, full-slide pass are discarded in favor of the second pass's
# crop-relative ones (see this module's docstring). Position accuracy
# doesn't matter for this pass's own numbers, only presence/absence.
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "objects": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["title", "paragraph", "equation", "diagram", "graph", "table", "image"],
                    },
                    "bounding_box": {
                        "type": "object",
                        "properties": {
                            "x": {"type": "number"},
                            "y": {"type": "number"},
                            "width": {"type": "number"},
                            "height": {"type": "number"},
                        },
                        "required": ["x", "y", "width", "height"],
                        "additionalProperties": False,
                    },
                    "extracted_text": {"type": ["string", "null"]},
                    "latex": {"type": ["string", "null"]},
                    "summary": {"type": ["string", "null"]},
                    "confidence": {"type": "number"},
                    "graph_nodes": {
                        "type": ["array", "null"],
                        "items": {
                            "type": "object",
                            "properties": {
                                "label": {"type": "string"},
                                "x": {"type": "number"},
                                "y": {"type": "number"},
                                "radius": {"type": "number"},
                            },
                            "required": ["label", "x", "y", "radius"],
                            "additionalProperties": False,
                        },
                    },
                    "graph_weight_labels": {
                        "type": ["array", "null"],
                        "items": {
                            "type": "object",
                            "properties": {
                                "value": {"type": "number"},
                                "x": {"type": "number"},
                                "y": {"type": "number"},
                            },
                            "required": ["value", "x", "y"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": [
                    "type",
                    "bounding_box",
                    "extracted_text",
                    "latex",
                    "summary",
                    "confidence",
                    "graph_nodes",
                    "graph_weight_labels",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["summary", "objects"],
    "additionalProperties": False,
}


def detect_media_type(image_bytes: bytes) -> str:
    if image_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if image_bytes[:2] == b"\xff\xd8":
        return "image/jpeg"
    # The extension always captures PNG (chrome.tabs.captureVisibleTab
    # defaults to "png" — see extension/src/service-worker/index.ts); this
    # fallback only matters for a future non-extension upload path.
    return "image/png"


def clamp_confidence(value: float) -> float:
    return max(0.0, min(1.0, value))


async def _build_graph_structure_safely(raw: dict, image_bytes: bytes, locate_graph_fn: LocateGraphFn) -> GraphStructure | None:
    """Runs the two-pass graph-localization + CV-topology pipeline, never
    letting a failure at any step (a second-pass API error, a malformed
    node list, an undecodable crop, etc.) fail the whole analysis — worst
    case, this object just doesn't get a graph_structure
    (docs/ARCHITECTURE.md §6 "never crash" applies here too).
    """
    if not raw.get("graph_nodes"):
        return None
    try:
        bounding_box = BoundingBox(**raw["bounding_box"])
        crop_bytes = crop_object_region(image_bytes, bounding_box)
        localized = await locate_graph_fn(crop_bytes)
        nodes = [RawGraphNode(**n) for n in localized["graph_nodes"]]
        weight_labels = [RawWeightLabel(**w) for w in localized["graph_weight_labels"]]
        return build_graph_structure(crop_bytes, nodes, weight_labels)
    except Exception:
        logger.warning("graph_structure_extraction_failed", exc_info=True)
        return None


async def to_slide_object(raw: dict, image_bytes: bytes, locate_graph_fn: LocateGraphFn) -> SlideObject:
    return SlideObject(
        id=str(uuid.uuid4()),
        type=raw["type"],
        bounding_box=BoundingBox(**raw["bounding_box"]),
        extracted_text=raw["extracted_text"],
        latex=raw["latex"],
        summary=raw["summary"],
        confidence=clamp_confidence(raw["confidence"]),
        graph_structure=await _build_graph_structure_safely(raw, image_bytes, locate_graph_fn),
    )


async def parse_analysis_payload(payload: dict, image_bytes: bytes, locate_graph_fn: LocateGraphFn) -> AnalysisResult:
    objects = [await to_slide_object(raw, image_bytes, locate_graph_fn) for raw in payload["objects"]]
    return AnalysisResult(objects=objects, summary=payload["summary"])
