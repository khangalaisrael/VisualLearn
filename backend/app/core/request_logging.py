"""One log line per request, and a last-resort handler for crashes.

The line carries the method, the route as written in the code (so
`/api/v1/notes/{note_id}`, never a real id or a query string), the status
and how long the request took. Nothing from the body or the headers is
logged: no keys, no session tokens, no slide content (app/core/logging.py).
A short request id ties the line to the traceback of a crash during it.

This is a plain ASGI middleware rather than `@app.middleware("http")`, so a
streamed chat reply passes through untouched; for a stream the time logged
is the whole stream's.
"""

import logging
import time
import uuid

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger("app.requests")

# Render polls this; a line for each poll would bury everything else.
QUIET_PATHS = frozenset({"/api/v1/health"})

CRASH_DETAIL = "Something went wrong on our side. Try again in a moment."


def _route(scope: Scope) -> str:
    """The path with each path parameter's value put back as its name. Built
    from the request rather than the matched route's own path, which in an
    included router lacks the prefix. A path no route matched is not logged
    at all: it is whatever a scanner happened to try."""
    if scope.get("route") is None:
        return "(no route)"
    path = scope.get("path", "")
    for name, value in (scope.get("path_params") or {}).items():
        path = path.replace(f"/{value}", f"/{{{name}}}", 1)
    return path


class RequestLoggingMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] in QUIET_PATHS:
            await self.app(scope, receive, send)
            return

        request_id = uuid.uuid4().hex[:8]
        scope.setdefault("state", {})["request_id"] = request_id
        started = time.perf_counter()
        status = 500

        async def send_and_note_status(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_and_note_status)
        finally:
            elapsed_ms = round((time.perf_counter() - started) * 1000)
            logger.info(
                "request id=%s method=%s route=%s status=%s elapsed_ms=%s",
                request_id,
                scope["method"],
                _route(scope),
                status,
                elapsed_ms,
            )


async def handle_crash(request: Request, exc: Exception) -> JSONResponse:
    """Any exception a route did not turn into an HTTP error. FastAPI's own
    HTTPException and validation errors never reach this."""
    request_id = getattr(request.state, "request_id", "-")
    logger.error(
        "crash id=%s method=%s route=%s error=%s",
        request_id,
        request.method,
        _route(request.scope),
        type(exc).__name__,
        exc_info=exc,
    )
    return JSONResponse(status_code=500, content={"detail": CRASH_DETAIL})
