"""Per-request model overrides (app/api/deps.py's resolve_* functions) on
real provider classes — the API-level tests only ever see the placeholder /
fake services from conftest.py, so the provider-matching rules are covered
here. No network: providers get injected AsyncMock clients, and overrides
only construct (never call) a new client.
"""

from collections.abc import Iterator
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.api.deps import resolve_chat_service, resolve_slide_analyzer
from app.core.config import get_settings
from app.services.claude_chat_service import ClaudeChatService
from app.services.claude_vlm_analyzer import ClaudeVLMAnalyzer
from app.services.openai_chat_service import OpenAIChatService
from app.services.openai_vlm_analyzer import OpenAIVLMAnalyzer


@pytest.fixture(autouse=True)
def _provider_keys(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_claude_services_default_to_haiku() -> None:
    assert ClaudeVLMAnalyzer(client=AsyncMock()).model_name == "claude-haiku-5-5"
    assert ClaudeChatService(client=AsyncMock()).model_name == "claude-haiku-5-5"


def test_settings_default_anthropic_models_to_haiku() -> None:
    settings = get_settings()
    assert settings.anthropic_vlm_model == "claude-haiku-5-5"
    assert settings.anthropic_chat_model == "claude-haiku-5-5"


def test_claude_backend_accepts_claude_override() -> None:
    default = ClaudeVLMAnalyzer(client=AsyncMock())
    resolved = resolve_slide_analyzer(default, "claude-sonnet-5-5")
    assert isinstance(resolved, ClaudeVLMAnalyzer)
    assert resolved.model_name == "claude-sonnet-5-5"

    chat = resolve_chat_service(ClaudeChatService(client=AsyncMock()), "claude-sonnet-5-5")
    assert isinstance(chat, ClaudeChatService)
    assert chat.model_name == "claude-sonnet-5-5"


def test_claude_backend_rejects_openai_override_with_actionable_message() -> None:
    with pytest.raises(HTTPException) as exc_info:
        resolve_slide_analyzer(ClaudeVLMAnalyzer(client=AsyncMock()), "gpt-4o")
    assert exc_info.value.status_code == 422
    assert "Server default" in exc_info.value.detail

    with pytest.raises(HTTPException) as exc_info:
        resolve_chat_service(ClaudeChatService(client=AsyncMock()), "gpt-4o")
    assert exc_info.value.status_code == 422


def test_openai_backend_rejects_claude_override() -> None:
    with pytest.raises(HTTPException) as exc_info:
        resolve_slide_analyzer(OpenAIVLMAnalyzer(client=AsyncMock()), "claude-haiku-5-5")
    assert exc_info.value.status_code == 422

    with pytest.raises(HTTPException) as exc_info:
        resolve_chat_service(OpenAIChatService(client=AsyncMock()), "claude-haiku-5-5")
    assert exc_info.value.status_code == 422


def test_openai_backend_still_accepts_openai_override() -> None:
    resolved = resolve_slide_analyzer(OpenAIVLMAnalyzer(client=AsyncMock()), "gpt-4o-mini")
    assert isinstance(resolved, OpenAIVLMAnalyzer)
    assert resolved.model_name == "gpt-4o-mini"


def test_no_override_keeps_default() -> None:
    default = ClaudeVLMAnalyzer(client=AsyncMock())
    assert resolve_slide_analyzer(default, None) is default
    assert resolve_slide_analyzer(default, "") is default
