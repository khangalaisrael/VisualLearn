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
    # Optional. Unset (the hosted default) means the analysis cache runs on
    # Postgres alone and nothing tries to reach Redis; docker-compose.yml
    # sets it for local runs.
    redis_url: str | None = None

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

    # Which Claude models ClaudeVLMAnalyzer / ClaudeChatService call when
    # Anthropic is the active provider (no OPENAI_API_KEY set). Claude Haiku
    # 5.5 is the default: ~$0.10/$0.50 per MTok, roughly 5x cheaper per
    # slide capture than gpt-4o-mini (whose image inputs are billed at a
    # large token multiplier) — see .env.example for the cost comparison.
    anthropic_vlm_model: str = "claude-haiku-5-5"
    anthropic_chat_model: str = "claude-haiku-5-5"

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

    # Phase 4 (docs/PublicHostingMVP.md) — per-user/per-IP daily caps on the
    # two expensive endpoints, enforced by app/services/rate_limiter.py.
    # "Generous" defaults picked for a single active student's realistic
    # daily use (several lecture captures across a few classes, a chat
    # question or two per slide) with real headroom — not a guess meant to
    # be tight, since the actual goal (per the doc) is stopping runaway/bot
    # abuse, not rationing normal use. Revisit once real usage is visible.
    rate_limit_captures_per_day: int = 20
    # Rolling 30-day allowance on top of the daily cap, so a month's spend is
    # bounded: users x this x cost per capture.
    rate_limit_captures_per_month: int = 400
    # "Resets at midnight" and "resets on the 1st" are evaluated in this
    # timezone for everyone (one fixed zone, not per-user).
    rate_limit_timezone: str = "Africa/Johannesburg"
    # Total captures per day across ALL non-admin users: a spike or a wave of
    # new sign-ups can't drain the AI balance. 250 is about $0.75/day at the
    # rough per-capture estimate.
    global_captures_per_day: int = 250
    rate_limit_chat_messages_per_day: int = 100

    # Chats (and the slide content behind them) are deleted this many days
    # after their last message — see services/retention.py.
    chat_retention_days: int = 30

    # Shown on the public privacy policy page (api/privacy.py). Set
    # PRIVACY_CONTACT_EMAIL on the host; without it the page points to the
    # store listing's support contact instead.
    privacy_contact_email: str | None = None

    # Comma-separated Google emails with no rate limits and access to the
    # admin page. Parsed by `admin_email_set` (pydantic-settings would expect
    # JSON for a list-typed field).
    admin_emails: str = ""

    # Rough USD per million tokens (input, output), only used to ESTIMATE
    # spend in usage_events. Check the provider's pricing page; unknown
    # models are costed at 0 rather than guessed.
    model_prices_usd_per_mtok: dict[str, tuple[float, float]] = {
        "claude-haiku-5-5": (0.10, 0.50),
        "claude-sonnet-5-5": (2.0, 10.0),
        "gpt-4o": (2.5, 10.0),
        "gpt-4o-mini": (0.15, 0.60),
    }

    @property
    def admin_email_set(self) -> frozenset[str]:
        return frozenset(e.strip().lower() for e in self.admin_emails.split(",") if e.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
