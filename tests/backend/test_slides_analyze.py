"""Tests for POST /slides/analyze (docs/API_CONTRACT.md §2)."""

import io

from httpx import AsyncClient
from PIL import Image

from app.core.config import get_settings


def _fake_png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (10, 10), color="white").save(buffer, format="PNG")
    return buffer.getvalue()


async def test_analyze_creates_presentation_and_slide(client: AsyncClient) -> None:
    files = {"image": ("slide.png", _fake_png_bytes(), "image/png")}
    data = {"slide_number": "1"}

    response = await client.post(
        "/api/v1/slides/analyze",
        files=files,
        data=data,
        headers={"X-API-Key": "test-api-key"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["cache_hit"] is False
    assert body["status"] == "analyzed"
    assert len(body["objects"]) == 1
    assert body["objects"][0]["type"] == "paragraph"
    assert "presentation_id" in body
    assert "slide_id" in body


async def test_analyze_treats_empty_string_presentation_id_as_omitted(client: AsyncClient) -> None:
    # Regression test: Swagger UI's "Try it out" form (and some other
    # multipart clients) submits "" for an untouched optional field rather
    # than omitting it — this must behave like presentation_id=None
    # (create a new presentation), not 422 on failed UUID parsing.
    response = await client.post(
        "/api/v1/slides/analyze",
        files={"image": ("slide.png", _fake_png_bytes(), "image/png")},
        data={"slide_number": "1", "presentation_id": ""},
        headers={"X-API-Key": "test-api-key"},
    )

    assert response.status_code == 200
    assert response.json()["cache_hit"] is False


async def test_analyze_same_image_in_same_presentation_is_cache_hit(client: AsyncClient) -> None:
    image_bytes = _fake_png_bytes()
    headers = {"X-API-Key": "test-api-key"}

    first = await client.post(
        "/api/v1/slides/analyze",
        files={"image": ("slide.png", image_bytes, "image/png")},
        data={"slide_number": "1"},
        headers=headers,
    )
    presentation_id = first.json()["presentation_id"]
    first_slide_id = first.json()["slide_id"]

    second = await client.post(
        "/api/v1/slides/analyze",
        files={"image": ("slide.png", image_bytes, "image/png")},
        data={"slide_number": "1", "presentation_id": presentation_id},
        headers=headers,
    )

    assert second.status_code == 200
    assert second.json()["cache_hit"] is True
    assert second.json()["presentation_id"] == presentation_id
    assert second.json()["slide_id"] == first_slide_id


async def test_analyze_different_image_in_same_presentation_is_not_cache_hit(client: AsyncClient) -> None:
    headers = {"X-API-Key": "test-api-key"}

    first = await client.post(
        "/api/v1/slides/analyze",
        files={"image": ("slide.png", _fake_png_bytes(), "image/png")},
        data={"slide_number": "1"},
        headers=headers,
    )
    presentation_id = first.json()["presentation_id"]

    other_buffer = io.BytesIO()
    Image.new("RGB", (10, 10), color="black").save(other_buffer, format="PNG")

    second = await client.post(
        "/api/v1/slides/analyze",
        files={"image": ("slide2.png", other_buffer.getvalue(), "image/png")},
        data={"slide_number": "2", "presentation_id": presentation_id},
        headers=headers,
    )

    assert second.status_code == 200
    assert second.json()["cache_hit"] is False
    assert second.json()["presentation_id"] == presentation_id


async def test_analyze_same_image_in_different_presentation_is_cache_hit(client: AsyncClient) -> None:
    """Milestone 2: the analysis cache is keyed globally by image hash, not
    scoped to a presentation (docs/services/cache_service.py) — an identical
    screenshot reappearing in an unrelated deck should still skip the
    (placeholder, in this test) analyzer call. This is what distinguishes
    `cache_hit` from the presentation-scoped Slide row de-duplication
    exercised by the same-presentation test above.
    """
    image_bytes = _fake_png_bytes()
    headers = {"X-API-Key": "test-api-key"}

    first = await client.post(
        "/api/v1/slides/analyze",
        files={"image": ("slide.png", image_bytes, "image/png")},
        data={"slide_number": "1"},
        headers=headers,
    )
    first_presentation_id = first.json()["presentation_id"]
    assert first.json()["cache_hit"] is False

    # No presentation_id — creates a brand-new, unrelated presentation.
    second = await client.post(
        "/api/v1/slides/analyze",
        files={"image": ("slide.png", image_bytes, "image/png")},
        data={"slide_number": "1"},
        headers=headers,
    )

    assert second.status_code == 200
    assert second.json()["presentation_id"] != first_presentation_id
    assert second.json()["cache_hit"] is True


async def test_analyze_requires_api_key(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/slides/analyze",
        files={"image": ("slide.png", _fake_png_bytes(), "image/png")},
        data={"slide_number": "1"},
    )
    assert response.status_code == 401


async def test_analyze_rejects_unknown_presentation_id(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/slides/analyze",
        files={"image": ("slide.png", _fake_png_bytes(), "image/png")},
        data={"slide_number": "1", "presentation_id": "00000000-0000-0000-0000-000000000000"},
        headers={"X-API-Key": "test-api-key"},
    )
    assert response.status_code == 404


async def test_analyze_rejects_empty_upload(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/slides/analyze",
        files={"image": ("slide.png", b"", "image/png")},
        data={"slide_number": "1"},
        headers={"X-API-Key": "test-api-key"},
    )
    assert response.status_code == 422


async def test_analyze_rejects_oversized_upload(client: AsyncClient) -> None:
    settings = get_settings()
    original_limit = settings.max_upload_bytes
    settings.max_upload_bytes = 1  # tiny limit to trigger 413 deterministically

    try:
        response = await client.post(
            "/api/v1/slides/analyze",
            files={"image": ("slide.png", _fake_png_bytes(), "image/png")},
            data={"slide_number": "1"},
            headers={"X-API-Key": "test-api-key"},
        )
        assert response.status_code == 413
    finally:
        settings.max_upload_bytes = original_limit


async def test_analyze_model_field_matching_default_is_a_no_op(client: AsyncClient) -> None:
    # PlaceholderSlideAnalyzer.model_name == "placeholder" (tests/backend/
    # conftest.py's override). Sending that back as `model` must behave
    # identically to omitting the field entirely.
    response = await client.post(
        "/api/v1/slides/analyze",
        files={"image": ("slide.png", _fake_png_bytes(), "image/png")},
        data={"slide_number": "1", "model": "placeholder"},
        headers={"X-API-Key": "test-api-key"},
    )
    assert response.status_code == 200
    assert response.json()["cache_hit"] is False


async def test_analyze_model_override_without_openai_backend_is_rejected(client: AsyncClient) -> None:
    # The active analyzer under test is PlaceholderSlideAnalyzer, not
    # OpenAIVLMAnalyzer — requesting a different real model must be
    # rejected (422), never silently ignored or, worse, allowed to
    # construct a real OpenAI client with no key configured.
    response = await client.post(
        "/api/v1/slides/analyze",
        files={"image": ("slide.png", _fake_png_bytes(), "image/png")},
        data={"slide_number": "1", "model": "gpt-4o-mini"},
        headers={"X-API-Key": "test-api-key"},
    )
    assert response.status_code == 422


async def test_analyze_rejects_unsupported_model_name(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/slides/analyze",
        files={"image": ("slide.png", _fake_png_bytes(), "image/png")},
        data={"slide_number": "1", "model": "not-a-real-model"},
        headers={"X-API-Key": "test-api-key"},
    )
    assert response.status_code == 422
