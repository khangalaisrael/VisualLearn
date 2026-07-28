"""Unit tests for ClaudeVLMAnalyzer.

These never call the real Anthropic API — a fake client with a mocked
`.messages.create` is injected instead (see the `client=` constructor
parameter, added specifically so this is possible without monkeypatching
the `anthropic` module).
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.services.claude_vlm_analyzer import ClaudeVLMAnalyzer


def _png_bytes() -> bytes:
    # The analyzer only inspects the header to pick a media type — it never
    # decodes the image — so a minimal magic-number prefix is sufficient.
    return b"\x89PNG\r\n\x1a\n" + b"rest-of-file-does-not-matter"


def _fake_response(payload: dict) -> SimpleNamespace:
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=json.dumps(payload))])


async def test_analyze_parses_response_into_slide_objects() -> None:
    payload = {
        "summary": "A slide about derivatives.",
        "objects": [
            {
                "type": "equation",
                "bounding_box": {"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.1},
                "extracted_text": None,
                "latex": "f'(x) = 2x",
                "summary": "The derivative of x^2.",
                "confidence": 0.92,
            },
            {
                "type": "title",
                "bounding_box": {"x": 0.0, "y": 0.0, "width": 1.0, "height": 0.1},
                "extracted_text": "Derivatives",
                "latex": None,
                "summary": None,
                "confidence": 0.99,
            },
        ],
    }
    fake_client = AsyncMock()
    fake_client.messages.create.return_value = _fake_response(payload)

    analyzer = ClaudeVLMAnalyzer(client=fake_client)
    result = await analyzer.analyze(_png_bytes())

    assert result.summary == "A slide about derivatives."
    assert len(result.objects) == 2
    assert result.objects[0].type == "equation"
    assert result.objects[0].latex == "f'(x) = 2x"
    assert result.objects[1].extracted_text == "Derivatives"
    # ids are server-generated, not taken from the model — and must be unique
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
                "summary": None,
                "confidence": 1.5,
            },
            {
                "type": "paragraph",
                "bounding_box": {"x": 0, "y": 0, "width": 1, "height": 1},
                "extracted_text": "y",
                "latex": None,
                "summary": None,
                "confidence": -0.2,
            },
        ],
    }
    fake_client = AsyncMock()
    fake_client.messages.create.return_value = _fake_response(payload)

    analyzer = ClaudeVLMAnalyzer(client=fake_client)
    result = await analyzer.analyze(_png_bytes())

    assert result.objects[0].confidence == 1.0
    assert result.objects[1].confidence == 0.0


async def test_analyze_sends_structured_output_request_with_correct_media_type() -> None:
    payload = {"summary": "s", "objects": []}
    fake_client = AsyncMock()
    fake_client.messages.create.return_value = _fake_response(payload)

    analyzer = ClaudeVLMAnalyzer(client=fake_client, model="claude-opus-4-8")
    await analyzer.analyze(_png_bytes())

    _, kwargs = fake_client.messages.create.call_args
    assert kwargs["model"] == "claude-opus-4-8"
    assert kwargs["output_config"]["format"]["type"] == "json_schema"
    assert kwargs["output_config"]["effort"] == "medium"

    image_block = kwargs["messages"][0]["content"][0]
    assert image_block["type"] == "image"
    assert image_block["source"]["media_type"] == "image/png"
    assert image_block["source"]["type"] == "base64"


def test_constructor_requires_api_key_or_client() -> None:
    try:
        ClaudeVLMAnalyzer()
    except ValueError as exc:
        assert "api_key or an injected client" in str(exc)
    else:
        raise AssertionError("expected ValueError when neither api_key nor client is provided")
