"""Shared FastAPI dependencies.

Kept out of individual routers so the routers stay thin (docs/ARCHITECTURE.md
§4: "api (routers) — thin, no business logic").
"""

import logging

from fastapi import Header, HTTPException, status

from app.core.config import get_settings
from app.services.chat_service import ChatService
from app.services.claude_chat_service import ClaudeChatService
from app.services.claude_vlm_analyzer import ClaudeVLMAnalyzer
from app.services.openai_chat_service import OpenAIChatService
from app.services.openai_vlm_analyzer import OpenAIVLMAnalyzer
from app.services.slide_analyzer import PlaceholderSlideAnalyzer, SlideAnalyzer

logger = logging.getLogger(__name__)


def _build_slide_analyzer() -> SlideAnalyzer:
    """Selects the active SlideAnalyzer implementation once at import time.

    Nothing else in the codebase depends on which concrete class this
    returns — only on the `SlideAnalyzer` protocol (docs/adr/ADR-004) — so
    this is the single place that decides which provider (or the
    placeholder) is actually active.

    OpenAI takes priority when both keys are set: it's the provider
    actually being paid for as of docs/adr/ADR-009-openai-as-active-vlm-provider.md
    (a billing/access decision, not a quality judgment — ClaudeVLMAnalyzer
    remains fully supported for anyone with Anthropic API access instead).
    """
    settings = get_settings()
    if settings.openai_api_key:
        return OpenAIVLMAnalyzer(api_key=settings.openai_api_key)
    if settings.anthropic_api_key:
        return ClaudeVLMAnalyzer(api_key=settings.anthropic_api_key)
    logger.warning(
        "Neither OPENAI_API_KEY nor ANTHROPIC_API_KEY is set — falling back to "
        "PlaceholderSlideAnalyzer. Set one in .env to enable real slide analysis "
        "(see docs/adr/ADR-009-openai-as-active-vlm-provider.md)."
    )
    return PlaceholderSlideAnalyzer()


_slide_analyzer = _build_slide_analyzer()


async def get_slide_analyzer() -> SlideAnalyzer:
    """Returns the active SlideAnalyzer implementation.

    Tests override this dependency directly (tests/backend/conftest.py) to
    guarantee they never call a real provider API regardless of whether
    OPENAI_API_KEY or ANTHROPIC_API_KEY happens to be set in the
    environment they run in.
    """
    return _slide_analyzer


def _build_chat_service() -> ChatService | None:
    """Selects the active ChatService implementation once at import time,
    mirroring `_build_slide_analyzer`'s OpenAI-first priority — extended
    here to chat (see docs/adr/ADR-009's note on this): the same billing
    reality (the project owner's only working key is OpenAI's) applies to
    chat, not just analysis, even though docs/ARCHITECTURE.md originally
    scoped that decision to analysis alone.

    Unlike slide analysis, there's no meaningful placeholder for chat — a
    canned response would actively mislead a student asking a real
    question — so `None` means chat is simply unavailable; the router
    returns 503 rather than serving a fake answer.
    """
    settings = get_settings()
    if settings.openai_api_key:
        return OpenAIChatService(api_key=settings.openai_api_key)
    if settings.anthropic_api_key:
        return ClaudeChatService(api_key=settings.anthropic_api_key)
    logger.warning(
        "Neither OPENAI_API_KEY nor ANTHROPIC_API_KEY is set — chat is unavailable. "
        "Set one in .env to enable POST /chat."
    )
    return None


_chat_service = _build_chat_service()


async def get_chat_service() -> ChatService | None:
    """Returns the active ChatService implementation, or None if no
    provider key is configured (see `_build_chat_service`). Tests override
    this dependency directly (tests/backend/conftest.py) to guarantee they
    never call a real provider API."""
    return _chat_service


async def verify_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Validates the shared local API key (docs/adr/ADR-007: no auth beyond
    a local key). `GET /health` is deliberately exempt from this dependency
    so container healthchecks and basic liveness probing don't need the
    secret — see docker-compose.yml's healthcheck and app/api/v1/health.py.
    """
    settings = get_settings()
    if not settings.local_api_key or x_api_key != settings.local_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing API key")
