"""Application configuration.

Single source of truth for environment-driven settings. See
docs/adr/ADR-007-local-first-deployment.md: the MVP has no auth beyond a
shared local API key, and the Anthropic API key lives only here — the
extension never holds it.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "local"
    log_level: str = "INFO"

    # Defaults target a non-Docker local run (e.g. `pytest`, or the backend
    # started directly on the host). docker-compose.yml overrides both via
    # container-network hostnames (`db`, `redis`).
    database_url: str = "postgresql+asyncpg://visionlearn:visionlearn@localhost:5432/visionlearn"
    redis_url: str = "redis://localhost:6379/0"

    # No default: a slide-analysis request without a configured key should be
    # loud (see services/health.py), not silently treated as "working".
    # Two providers are supported behind the same SlideAnalyzer protocol
    # (docs/adr/ADR-004-vlm-first-pipeline.md); which one is actually active
    # is a billing/access decision, not an architecture one — see
    # docs/adr/ADR-009-openai-as-active-vlm-provider.md and the selection
    # logic in app/api/deps.py.
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None

    # Which OpenAI model OpenAIVLMAnalyzer calls for slide capture analysis.
    # "gpt-4o" (default) is the higher-accuracy, higher-cost option; "gpt-4o-mini"
    # is ~16x cheaper per token but weaker at dense equation/diagram reading —
    # see docs/adr/ADR-009-openai-as-active-vlm-provider.md. Does not affect
    # chat — see openai_chat_model below.
    openai_vlm_model: str = "gpt-4o"

    # Which OpenAI model OpenAIChatService calls for Ask-tab chat. Same
    # gpt-4o / gpt-4o-mini tradeoff as openai_vlm_model above, set
    # independently since capture accuracy and chat accuracy needs may differ.
    openai_chat_model: str = "gpt-4o"

    # Shared secret between the extension and this backend (see ADR-007).
    # CORS is intentionally left open (see main.py) — this header is the
    # actual access control for a locally-run, single-user backend.
    local_api_key: str | None = None

    # Security non-functional requirement (docs/ARCHITECTURE.md §6): limit
    # upload size. 8 MB comfortably covers a full-resolution slide capture.
    max_upload_bytes: int = 8 * 1024 * 1024

    cors_allow_origins: list[str] = ["*"]

    # Optional override for app/core/prompt_loader.py. Left unset, the loader
    # computes the repo-root `prompts/` directory from its own file location
    # (correct in both local dev and Docker — see backend/Dockerfile's
    # comment on why the container preserves the same directory nesting).
    prompts_dir: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
