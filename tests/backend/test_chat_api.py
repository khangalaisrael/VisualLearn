"""Tests for POST /chat (docs/API_CONTRACT.md §3). Uses the `client` fixture
from conftest.py, which already overrides get_chat_service with
FakeChatService — no real provider API is ever called."""

import io
import json

from httpx import AsyncClient
from PIL import Image

_HEADERS = {"X-API-Key": "test-api-key"}


def _fake_png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (10, 10), color="white").save(buffer, format="PNG")
    return buffer.getvalue()


async def _analyze_slide(client: AsyncClient) -> dict:
    response = await client.post(
        "/api/v1/slides/analyze",
        files={"image": ("slide.png", _fake_png_bytes(), "image/png")},
        data={"slide_number": "1"},
        headers=_HEADERS,
    )
    assert response.status_code == 200
    return response.json()


def _parse_sse(text: str) -> list[tuple[str, dict]]:
    """Parses the raw SSE body into a list of (event_name, data_dict) pairs."""
    events = []
    for block in text.strip().split("\n\n"):
        if not block.strip():
            continue
        lines = block.strip().splitlines()
        event_name = next(line.removeprefix("event: ") for line in lines if line.startswith("event: "))
        data_line = next(line.removeprefix("data: ") for line in lines if line.startswith("data: "))
        events.append((event_name, json.loads(data_line)))
    return events


async def test_chat_figure_mode_streams_answer(client: AsyncClient) -> None:
    analysis = await _analyze_slide(client)
    object_id = analysis["objects"][0]["id"]

    response = await client.post(
        "/api/v1/chat",
        json={
            "presentation_id": analysis["presentation_id"],
            "query_mode": "figure",
            "slide_id": analysis["slide_id"],
            "object_id": object_id,
            "message": "What is this?",
        },
        headers=_HEADERS,
    )

    assert response.status_code == 200
    events = _parse_sse(response.text)
    deltas = [data["text"] for name, data in events if name == "delta"]
    assert deltas == ["Fake ", "answer."]
    done_events = [data for name, data in events if name == "done"]
    assert len(done_events) == 1
    assert done_events[0]["referenced_object_ids"] == [object_id]
    assert done_events[0]["usage"]["input_tokens"] == 10
    assert "conversation_id" in done_events[0]
    assert "message_id" in done_events[0]


async def test_chat_slide_mode_streams_answer(client: AsyncClient) -> None:
    analysis = await _analyze_slide(client)

    response = await client.post(
        "/api/v1/chat",
        json={
            "presentation_id": analysis["presentation_id"],
            "query_mode": "slide",
            "slide_id": analysis["slide_id"],
            "message": "Summarize this slide.",
        },
        headers=_HEADERS,
    )

    assert response.status_code == 200
    events = _parse_sse(response.text)
    done_events = [data for name, data in events if name == "done"]
    assert len(done_events) == 1
    assert done_events[0]["referenced_object_ids"] == [analysis["objects"][0]["id"]]


async def test_chat_figure_mode_requires_object_id(client: AsyncClient) -> None:
    analysis = await _analyze_slide(client)

    response = await client.post(
        "/api/v1/chat",
        json={
            "presentation_id": analysis["presentation_id"],
            "query_mode": "figure",
            "slide_id": analysis["slide_id"],
            "message": "What is this?",
        },
        headers=_HEADERS,
    )
    assert response.status_code == 400


async def test_chat_rejects_unsupported_query_mode(client: AsyncClient) -> None:
    analysis = await _analyze_slide(client)

    response = await client.post(
        "/api/v1/chat",
        json={
            "presentation_id": analysis["presentation_id"],
            "query_mode": "presentation",
            "message": "What is this deck about?",
        },
        headers=_HEADERS,
    )
    assert response.status_code == 400


async def test_chat_rejects_unknown_object_id(client: AsyncClient) -> None:
    analysis = await _analyze_slide(client)

    response = await client.post(
        "/api/v1/chat",
        json={
            "presentation_id": analysis["presentation_id"],
            "query_mode": "figure",
            "slide_id": analysis["slide_id"],
            "object_id": "00000000-0000-0000-0000-000000000000",
            "message": "What is this?",
        },
        headers=_HEADERS,
    )
    assert response.status_code == 404


async def test_chat_rejects_unknown_presentation_id(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/chat",
        json={
            "presentation_id": "00000000-0000-0000-0000-000000000000",
            "query_mode": "slide",
            "slide_id": "00000000-0000-0000-0000-000000000000",
            "message": "hi",
        },
        headers=_HEADERS,
    )
    assert response.status_code == 404


async def test_chat_requires_api_key(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/chat",
        json={"query_mode": "slide", "message": "hi"},
    )
    assert response.status_code == 401


async def test_analyze_same_image_second_presentation_does_not_collide_on_object_ids(client: AsyncClient) -> None:
    """Regression test: the same image analyzed under two different
    presentations is a cache hit (image-hash cache is global), but each
    presentation's Slide row needs its own objects rows — this must not
    raise a primary-key collision (see ObjectRepository's docstring)."""
    image_bytes = _fake_png_bytes()

    first = await client.post(
        "/api/v1/slides/analyze",
        files={"image": ("slide.png", image_bytes, "image/png")},
        data={"slide_number": "1"},
        headers=_HEADERS,
    )
    second = await client.post(
        "/api/v1/slides/analyze",
        files={"image": ("slide.png", image_bytes, "image/png")},
        data={"slide_number": "1"},
        headers=_HEADERS,
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["cache_hit"] is True
    assert second.json()["objects"][0]["id"] != first.json()["objects"][0]["id"]


async def test_chat_model_field_matching_default_is_a_no_op(client: AsyncClient) -> None:
    # FakeChatService.model_name == "fake-chat-model" (tests/backend/
    # conftest.py's override). Sending that back as `model` must behave
    # identically to omitting the field entirely.
    analysis = await _analyze_slide(client)

    response = await client.post(
        "/api/v1/chat",
        json={
            "presentation_id": analysis["presentation_id"],
            "query_mode": "slide",
            "slide_id": analysis["slide_id"],
            "message": "What is this?",
            "model": "fake-chat-model",
        },
        headers=_HEADERS,
    )
    assert response.status_code == 200
    events = _parse_sse(response.text)
    assert events[-1][0] == "done"


async def test_chat_model_override_without_openai_backend_is_rejected(client: AsyncClient) -> None:
    # The active chat service under test is FakeChatService, not
    # OpenAIChatService — requesting a different real model must be
    # rejected (422), never silently ignored or allowed to construct a
    # real OpenAI client with no key configured.
    analysis = await _analyze_slide(client)

    response = await client.post(
        "/api/v1/chat",
        json={
            "presentation_id": analysis["presentation_id"],
            "query_mode": "slide",
            "slide_id": analysis["slide_id"],
            "message": "What is this?",
            "model": "gpt-4o-mini",
        },
        headers=_HEADERS,
    )
    assert response.status_code == 422
