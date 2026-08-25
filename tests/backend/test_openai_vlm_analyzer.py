"""Unit tests for OpenAIVLMAnalyzer.

Mirrors tests/backend/test_claude_vlm_analyzer.py. These never call the
real OpenAI API — a fake client with a mocked `.chat.completions.create` is
injected instead (see the `client=` constructor parameter).
"""

import io
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

from PIL import Image, ImageDraw

from app.services.openai_vlm_analyzer import OpenAIVLMAnalyzer


def _png_bytes() -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"rest-of-file-does-not-matter"


def _line_graph_png() -> tuple[bytes, int, int]:
    """A real (decodable) image with two nodes connected by a line — used
    to test the full analyze() -> parse_analysis_payload -> graph_topology
    chain end-to-end, not just with mocked CV output."""
    width, height = 300, 150
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    draw.line([(50, 75), (250, 75)], fill="black", width=3)
    draw.ellipse([30, 55, 70, 95], fill="lightblue", outline="black")
    draw.ellipse([230, 55, 270, 95], fill="lightblue", outline="black")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue(), width, height


def _fake_response(payload: dict, *, refusal: str | None = None) -> SimpleNamespace:
    message = SimpleNamespace(content=json.dumps(payload) if refusal is None else None, refusal=refusal)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


async def test_analyze_parses_response_into_slide_objects() -> None:
    payload = {
        "summary": "A slide about derivatives.",
        "objects": [
            {
                "type": "equation",
                "bounding_box": {"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.1},
                "extracted_text": None,
                "latex": "f'(x) = 2x",
                "language": None,
                "summary": "The derivative of x^2.",
                "confidence": 0.92,
            },
            {
                "type": "title",
                "bounding_box": {"x": 0.0, "y": 0.0, "width": 1.0, "height": 0.1},
                "extracted_text": "Derivatives",
                "latex": None,
                "language": None,
                "summary": None,
                "confidence": 0.99,
            },
        ],
    }
    fake_client = AsyncMock()
    fake_client.chat.completions.create.return_value = _fake_response(payload)

    analyzer = OpenAIVLMAnalyzer(client=fake_client)
    result = await analyzer.analyze(_png_bytes())

    assert result.summary == "A slide about derivatives."
    assert len(result.objects) == 2
    assert result.objects[0].type == "equation"
    assert result.objects[0].latex == "f'(x) = 2x"
    assert result.objects[1].extracted_text == "Derivatives"
    assert result.objects[0].id != result.objects[1].id


async def test_analyze_clamps_out_of_range_confidence() -> None:
    payload = {
        "summary": "s",
        "objects": [
            {
                "type": "paragraph",
                "bounding_box": {"x": 0, "y": 0, "width": 1, "height": 1},
                "extracted_text": "x",
                "latex": None,
                "language": None,
                "summary": None,
                "confidence": 1.5,
            }
        ],
    }
    fake_client = AsyncMock()
    fake_client.chat.completions.create.return_value = _fake_response(payload)

    analyzer = OpenAIVLMAnalyzer(client=fake_client)
    result = await analyzer.analyze(_png_bytes())

    assert result.objects[0].confidence == 1.0


async def test_analyze_sends_structured_output_request_with_correct_media_type() -> None:
    payload = {"summary": "s", "objects": []}
    fake_client = AsyncMock()
    fake_client.chat.completions.create.return_value = _fake_response(payload)

    analyzer = OpenAIVLMAnalyzer(client=fake_client, model="gpt-4o")
    await analyzer.analyze(_png_bytes())

    _, kwargs = fake_client.chat.completions.create.call_args
    assert kwargs["model"] == "gpt-4o"
    assert kwargs["response_format"]["type"] == "json_schema"
    assert kwargs["response_format"]["json_schema"]["strict"] is True

    image_part = kwargs["messages"][1]["content"][1]
    assert image_part["type"] == "image_url"
    assert image_part["image_url"]["url"].startswith("data:image/png;base64,")


async def test_analyze_raises_on_refusal() -> None:
    fake_client = AsyncMock()
    fake_client.chat.completions.create.return_value = _fake_response(
        {}, refusal="I can't help with that."
    )

    analyzer = OpenAIVLMAnalyzer(client=fake_client)

    try:
        await analyzer.analyze(_png_bytes())
    except RuntimeError as exc:
        assert "declined" in str(exc)
    else:
        raise AssertionError("expected RuntimeError on refusal")


async def test_analyze_builds_graph_structure_end_to_end() -> None:
    """Integration test (docs/adr/ADR-010): exercises the real two-pass CV
    pipeline (crop_object_region + graph_topology), not a mocked one — only
    the two OpenAI calls themselves are faked. The first call's own
    graph_nodes are just the trigger signal (see vlm_output.py); the
    second (mocked) call supplies the positions actually used."""
    image_bytes, width, height = _line_graph_png()
    analysis_payload = {
        "summary": "A simple two-node graph.",
        "objects": [
            {
                "type": "diagram",
                "bounding_box": {"x": 0, "y": 0, "width": 1, "height": 1},
                "extracted_text": None,
                "latex": None,
                "language": None,
                "summary": "Two nodes connected by an edge.",
                "confidence": 0.95,
                "graph_nodes": [{"label": "placeholder", "x": 0.5, "y": 0.5, "radius": 0.1}],
                "graph_weight_labels": None,
            }
        ],
    }
    localization_payload = {
        "graph_nodes": [
            {"label": "A", "x": 50 / width, "y": 75 / height, "radius": 20 / width},
            {"label": "B", "x": 250 / width, "y": 75 / height, "radius": 20 / width},
        ],
        "graph_weight_labels": [],
    }
    fake_client = AsyncMock()
    fake_client.chat.completions.create.side_effect = [
        _fake_response(analysis_payload),
        _fake_response(localization_payload),
    ]

    analyzer = OpenAIVLMAnalyzer(client=fake_client)
    result = await analyzer.analyze(image_bytes)

    structure = result.objects[0].graph_structure
    assert structure is not None
    assert structure.nodes == ["A", "B"]
    assert len(structure.edges) == 1
    assert {structure.edges[0].node_a, structure.edges[0].node_b} == {"A", "B"}
    assert fake_client.chat.completions.create.call_count == 2


def test_constructor_requires_api_key_or_client() -> None:
    try:
        OpenAIVLMAnalyzer()
    except ValueError as exc:
        assert "api_key or an injected client" in str(exc)
    else:
        raise AssertionError("expected ValueError when neither api_key nor client is provided")
