"""The per-request log line and the last-resort crash handler (app/core/request_logging.py)."""

import io
import logging

from fastapi import APIRouter
from httpx import ASGITransport, AsyncClient
from PIL import Image

from app.core.request_logging import CRASH_DETAIL, RequestLoggingMiddleware
from app.main import app

API_KEY = {"X-API-Key": "test-api-key"}


def _request_lines(caplog) -> list[str]:
    return [record.getMessage() for record in caplog.records if record.name == "app.requests"]


async def test_each_request_is_logged_with_its_route_and_status(client: AsyncClient, caplog) -> None:
    caplog.set_level(logging.INFO, logger="app.requests")

    await client.get("/api/v1/notes/abc", headers=API_KEY)  # signed out: 401

    [line] = _request_lines(caplog)
    assert "method=GET" in line
    assert "route=/api/v1/notes/{note_id}" in line  # the route, never the id in it
    assert "status=" in line and "elapsed_ms=" in line


async def test_health_checks_are_not_logged(client: AsyncClient, caplog) -> None:
    caplog.set_level(logging.INFO, logger="app.requests")

    assert (await client.get("/api/v1/health")).status_code == 200

    assert _request_lines(caplog) == []


async def test_a_crash_gets_a_plain_500_and_its_traceback_is_logged(client: AsyncClient, caplog) -> None:
    caplog.set_level(logging.INFO, logger="app.requests")
    router = APIRouter()

    @router.get("/api/v1/test-crash")
    async def crash() -> None:
        raise RuntimeError("boom")

    app.include_router(router)
    try:
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as crashing:
            response = await crashing.get("/api/v1/test-crash")
    finally:
        app.router.routes[:] = [r for r in app.router.routes if getattr(r, "path", None) != "/api/v1/test-crash"]

    assert response.status_code == 500
    assert response.json() == {"detail": CRASH_DETAIL}
    crash_records = [r for r in caplog.records if r.name == "app.requests" and r.getMessage().startswith("crash")]
    assert len(crash_records) == 1
    assert crash_records[0].exc_info is not None
    assert "error=RuntimeError" in crash_records[0].getMessage()
    assert any("status=500" in line for line in _request_lines(caplog))


async def test_a_streamed_reply_passes_through_piece_by_piece(caplog) -> None:
    """httpx's test transport gathers a response into one body, so the
    middleware is driven directly: each piece the app sends must reach the
    server as its own message, in order, before the request is logged."""
    caplog.set_level(logging.INFO, logger="app.requests")
    sent: list[dict] = []

    async def streaming_app(scope, receive, send) -> None:
        scope["route"] = object()  # as if a route matched
        await send({"type": "http.response.start", "status": 200, "headers": []})
        for piece in (b"event: delta\n\n", b"event: done\n\n"):
            await send({"type": "http.response.body", "body": piece, "more_body": True})
            assert _request_lines(caplog) == []  # not logged until the stream ends
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    async def record(message: dict) -> None:
        sent.append(message)

    async def no_body() -> dict:
        return {"type": "http.request", "body": b"", "more_body": False}

    scope = {"type": "http", "method": "POST", "path": "/api/v1/chat", "headers": []}
    await RequestLoggingMiddleware(streaming_app)(scope, no_body, record)

    assert [m.get("body") for m in sent] == [None, b"event: delta\n\n", b"event: done\n\n", b""]
    [line] = _request_lines(caplog)
    assert "route=/api/v1/chat" in line and "status=200" in line


async def test_a_chat_request_is_logged_under_its_full_route(client: AsyncClient, caplog) -> None:
    caplog.set_level(logging.INFO, logger="app.requests")
    buffer = io.BytesIO()
    Image.new("RGB", (10, 10), color="white").save(buffer, format="PNG")
    captured = (
        await client.post(
            "/api/v1/slides/analyze",
            files={"image": ("slide.png", buffer.getvalue(), "image/png")},
            data={"slide_number": "1"},
            headers=API_KEY,
        )
    ).json()

    response = await client.post(
        "/api/v1/chat",
        json={
            "presentation_id": captured["presentation_id"],
            "query_mode": "slide",
            "slide_id": captured["slide_id"],
            "message": "Summarize this slide.",
        },
        headers=API_KEY,
    )

    assert response.status_code == 200
    lines = _request_lines(caplog)
    assert any("route=/api/v1/slides/analyze" in line and "status=200" in line for line in lines)
    assert any("route=/api/v1/chat" in line and "status=200" in line for line in lines)


async def test_a_path_no_route_matches_is_not_echoed(client: AsyncClient, caplog) -> None:
    caplog.set_level(logging.INFO, logger="app.requests")

    await client.get("/wp-admin/secret-scan", headers=API_KEY)

    [line] = _request_lines(caplog)
    assert "route=(no route)" in line and "wp-admin" not in line
