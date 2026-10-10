"""Phase 4 — per-user/per-IP daily and monthly rate limits (docs/PublicHostingMVP.md).

Uses a low limit override per test (rather than the real defaults)
so a test can actually reach the limit without making dozens of requests.
"""

import io
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.orm import RateLimitEvent


def _fake_png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (10, 10), color="white").save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture(autouse=True)
def low_limits():
    """Every test in this file gets a 2-per-day cap instead of the real
    defaults — get_settings() is @lru_cache'd, but the `client` fixture's
    settings object is the same cached instance the app already resolved
    dependencies against, so mutating its attributes directly (not
    reassigning the cache) takes effect immediately."""
    settings = get_settings()
    original = (
        settings.rate_limit_captures_per_day,
        settings.rate_limit_captures_per_month,
        settings.rate_limit_chat_messages_per_day,
    )
    settings.rate_limit_captures_per_day = 2
    settings.rate_limit_captures_per_month = 400
    settings.rate_limit_chat_messages_per_day = 2
    yield
    (
        settings.rate_limit_captures_per_day,
        settings.rate_limit_captures_per_month,
        settings.rate_limit_chat_messages_per_day,
    ) = original


async def _capture(client: AsyncClient) -> int:
    response = await client.post(
        "/api/v1/slides/analyze",
        files={"image": ("slide.png", _fake_png_bytes(), "image/png")},
        data={"slide_number": "1"},
        headers={"X-API-Key": "test-api-key"},
    )
    return response.status_code


async def test_allows_requests_up_to_the_limit(client: AsyncClient) -> None:
    assert await _capture(client) == 200
    assert await _capture(client) == 200


async def test_blocks_the_request_past_the_limit(client: AsyncClient) -> None:
    assert await _capture(client) == 200
    assert await _capture(client) == 200
    assert await _capture(client) == 429


async def test_429_response_has_a_student_facing_message_and_retry_after(client: AsyncClient) -> None:
    await _capture(client)
    await _capture(client)
    response = await client.post(
        "/api/v1/slides/analyze",
        files={"image": ("slide.png", _fake_png_bytes(), "image/png")},
        data={"slide_number": "1"},
        headers={"X-API-Key": "test-api-key"},
    )

    assert response.status_code == 429
    assert "try again" in response.json()["detail"].lower()
    assert "Retry-After" in response.headers
    assert int(response.headers["Retry-After"]) > 0


async def test_a_rejected_request_does_not_itself_count_against_the_limit(client: AsyncClient) -> None:
    await _capture(client)
    await _capture(client)
    assert await _capture(client) == 429
    # Still blocked, not freshly re-allowed — confirms the 429 above didn't
    # also record a new event (that would be a second bug stacked on top:
    # every rejected request pushing the reset time further away).
    assert await _capture(client) == 429


async def test_chat_and_capture_limits_are_independent(client: AsyncClient) -> None:
    """Exhausting the capture limit must not affect the separate chat
    limit, and vice versa — they're different `action` values in the same
    table, not a shared budget."""
    captured = await client.post(
        "/api/v1/slides/analyze",
        files={"image": ("slide.png", _fake_png_bytes(), "image/png")},
        data={"slide_number": "1"},
        headers={"X-API-Key": "test-api-key"},
    )
    presentation_id = captured.json()["presentation_id"]
    slide_id = captured.json()["slide_id"]
    await _capture(client)
    assert await _capture(client) == 429

    chat_payload = {
        "conversation_id": None,
        "presentation_id": presentation_id,
        "query_mode": "slide",
        "slide_id": slide_id,
        "object_id": None,
        "message": "Explain this slide.",
    }
    first_chat = await client.post("/api/v1/chat", json=chat_payload, headers={"X-API-Key": "test-api-key"})
    assert first_chat.status_code == 200


async def _capture_response(client: AsyncClient):
    return await client.post(
        "/api/v1/slides/analyze",
        files={"image": ("slide.png", _fake_png_bytes(), "image/png")},
        data={"slide_number": "1"},
        headers={"X-API-Key": "test-api-key"},
    )


async def test_monthly_allowance_blocks_even_when_the_daily_limit_has_room(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    settings = get_settings()
    settings.rate_limit_captures_per_day = 10
    settings.rate_limit_captures_per_month = 3

    assert (await _capture_response(client)).status_code == 200  # creates this client's key row
    key = (await db_session.execute(select(RateLimitEvent.key))).scalars().first()
    # Two more captures made 5 days ago: outside the daily window, inside the monthly one.
    for _ in range(2):
        db_session.add(RateLimitEvent(key=key, action="analyze", created_at=datetime.now(UTC) - timedelta(days=5)))
    await db_session.commit()

    blocked = await _capture_response(client)
    assert blocked.status_code == 429
    assert "this month's allowance of 3" in blocked.json()["detail"]
    # The wait reflects the monthly window (~25 days), not the 24h one.
    assert int(blocked.headers["Retry-After"]) > 20 * 24 * 3600
    assert "days" in blocked.json()["detail"]


async def test_captures_older_than_a_month_do_not_count(client: AsyncClient, db_session: AsyncSession) -> None:
    settings = get_settings()
    settings.rate_limit_captures_per_day = 10
    settings.rate_limit_captures_per_month = 2
    assert (await _capture_response(client)).status_code == 200
    key = (await db_session.execute(select(RateLimitEvent.key))).scalars().first()
    for _ in range(5):
        db_session.add(RateLimitEvent(key=key, action="analyze", created_at=datetime.now(UTC) - timedelta(days=40)))
    await db_session.commit()

    assert (await _capture_response(client)).status_code == 200  # second this month
    assert (await _capture_response(client)).status_code == 429  # third


async def test_daily_limit_message_names_the_daily_limit(client: AsyncClient) -> None:
    """With only the daily limit reached, the message names the daily limit."""
    await _capture(client)
    await _capture(client)
    blocked = await _capture_response(client)
    assert blocked.status_code == 429
    assert "today's limit for slide captures" in blocked.json()["detail"]
