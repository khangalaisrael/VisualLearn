"""Unit tests for vlm_output.py's graph_structure integration
(docs/adr/ADR-010-hybrid-graph-structure-extraction.md), including the
two-pass localization flow: pass 1's own graph_nodes/graph_weight_labels
are only a trigger signal (see the module docstring) — the positions
actually used come from `locate_graph_fn`, a mocked second-pass call here."""

import io

from PIL import Image, ImageDraw

from app.services.vlm_output import parse_analysis_payload


def _make_line_image() -> tuple[bytes, int, int]:
    width, height = 300, 150
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    draw.line([(50, 75), (250, 75)], fill="black", width=3)
    draw.ellipse([30, 55, 70, 95], fill="lightblue", outline="black")
    draw.ellipse([230, 55, 270, 95], fill="lightblue", outline="black")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue(), width, height


async def test_parse_analysis_payload_builds_graph_structure_when_present() -> None:
    image_bytes, width, height = _make_line_image()
    payload = {
        "summary": "s",
        "objects": [
            {
                "type": "diagram",
                "bounding_box": {"x": 0, "y": 0, "width": 1, "height": 1},
                "extracted_text": None,
                "latex": None,
                "language": None,
                "summary": "a graph",
                "confidence": 0.9,
                # Trigger only — discarded in favor of locate_graph_fn's response.
                "graph_nodes": [{"label": "placeholder", "x": 0.5, "y": 0.5, "radius": 0.1}],
                "graph_weight_labels": None,
            }
        ],
    }

    async def locate_graph_fn(_crop_bytes: bytes) -> dict:
        return {
            "graph_nodes": [
                {"label": "A", "x": 50 / width, "y": 75 / height, "radius": 20 / width},
                {"label": "B", "x": 250 / width, "y": 75 / height, "radius": 20 / width},
            ],
            "graph_weight_labels": [],
        }

    result = await parse_analysis_payload(payload, image_bytes, locate_graph_fn)

    obj = result.objects[0]
    assert obj.graph_structure is not None
    assert obj.graph_structure.nodes == ["A", "B"]
    assert len(obj.graph_structure.edges) == 1


async def test_parse_analysis_payload_leaves_graph_structure_none_without_graph_nodes() -> None:
    image_bytes, _width, _height = _make_line_image()
    payload = {
        "summary": "s",
        "objects": [
            {
                "type": "paragraph",
                "bounding_box": {"x": 0, "y": 0, "width": 1, "height": 1},
                "extracted_text": "hello",
                "latex": None,
                "language": None,
                "summary": None,
                "confidence": 0.9,
                # graph_nodes / graph_weight_labels omitted, as a real
                # analyzer response would for a non-graph object.
            }
        ],
    }

    async def locate_graph_fn(_crop_bytes: bytes) -> dict:
        raise AssertionError("locate_graph_fn must not be called without a graph_nodes trigger")

    result = await parse_analysis_payload(payload, image_bytes, locate_graph_fn)

    assert result.objects[0].graph_structure is None


async def test_parse_analysis_payload_tolerates_malformed_localization_response() -> None:
    image_bytes, _width, _height = _make_line_image()
    payload = {
        "summary": "s",
        "objects": [
            {
                "type": "diagram",
                "bounding_box": {"x": 0, "y": 0, "width": 1, "height": 1},
                "extracted_text": None,
                "latex": None,
                "language": None,
                "summary": None,
                "confidence": 0.9,
                "graph_nodes": [{"label": "placeholder", "x": 0.5, "y": 0.5, "radius": 0.1}],
                "graph_weight_labels": None,
            }
        ],
    }

    async def locate_graph_fn(_crop_bytes: bytes) -> dict:
        return {"graph_nodes": [{"label": "A"}], "graph_weight_labels": None}  # missing required x/y/radius

    # Must not raise — a CV/parsing failure degrades to graph_structure=None,
    # not a 500 (docs/ARCHITECTURE.md §6 "never crash").
    result = await parse_analysis_payload(payload, image_bytes, locate_graph_fn)
    assert result.objects[0].graph_structure is None


async def test_parse_analysis_payload_tolerates_locate_graph_fn_error() -> None:
    image_bytes, _width, _height = _make_line_image()
    payload = {
        "summary": "s",
        "objects": [
            {
                "type": "diagram",
                "bounding_box": {"x": 0, "y": 0, "width": 1, "height": 1},
                "extracted_text": None,
                "latex": None,
                "language": None,
                "summary": None,
                "confidence": 0.9,
                "graph_nodes": [{"label": "placeholder", "x": 0.5, "y": 0.5, "radius": 0.1}],
                "graph_weight_labels": None,
            }
        ],
    }

    async def locate_graph_fn(_crop_bytes: bytes) -> dict:
        raise RuntimeError("simulated second-pass API failure")

    result = await parse_analysis_payload(payload, image_bytes, locate_graph_fn)
    assert result.objects[0].graph_structure is None


async def test_parse_analysis_payload_round_trips_code_object_language() -> None:
    image_bytes, _width, _height = _make_line_image()
    payload = {
        "summary": "s",
        "objects": [
            {
                "type": "code",
                "bounding_box": {"x": 0, "y": 0, "width": 1, "height": 1},
                "extracted_text": "def f(x):\n    return x ** 2",
                "latex": None,
                "language": "python",
                "summary": "A squaring function.",
                "confidence": 0.9,
            }
        ],
    }

    async def locate_graph_fn(_crop_bytes: bytes) -> dict:
        raise AssertionError("locate_graph_fn must not be called for a non-graph object")

    result = await parse_analysis_payload(payload, image_bytes, locate_graph_fn)

    obj = result.objects[0]
    assert obj.type == "code"
    assert obj.language == "python"
    assert obj.extracted_text == "def f(x):\n    return x ** 2"
