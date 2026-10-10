"""Shared FastAPI dependencies.

Kept out of individual routers so the routers stay thin (docs/ARCHITECTURE.md
§4: "api (routers) — thin, no business logic").
"""

import logging
import uuid

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_db
from app.models.orm import Presentation, User
from app.core import clock
from app.repositories.rate_limit_events import RateLimitEventRepository
from app.repositories.sessions import SessionRepository
from app.repositories.usage_events import UsageEventRepository
from app.services.chat_service import ChatService
from app.services.claude_chat_service import ClaudeChatService
from app.services.claude_vlm_analyzer import ClaudeVLMAnalyzer
from app.services.openai_chat_service import OpenAIChatService
from app.services.openai_vlm_analyzer import OpenAIVLMAnalyzer
from app.services.rate_limiter import (
    RateLimitExceeded,
    capture_limits,
    chat_limits,
    enforce_global_capture_cap,
    enforce_rate_limits,
)
from app.services.slide_analyzer import PlaceholderSlideAnalyzer, SlideAnalyzer

logger = logging.getLogger(__name__)

# Models the extension's Settings-tab picker is allowed to request per
# capture/chat call (see SettingsTab.tsx), per provider. Constrained rather
# than free-text so a typo can't reach a provider API and produce an opaque
# error. An override only applies when it belongs to the provider that is
# actually configured — a backend has one active provider's key.
_ALLOWED_OPENAI_MODELS = {"gpt-4o", "gpt-4o-mini"}
_ALLOWED_CLAUDE_MODELS = {"claude-haiku-5-5", "claude-sonnet-5-5"}


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
        return OpenAIVLMAnalyzer(api_key=settings.openai_api_key, model=settings.openai_vlm_model)
    if settings.anthropic_api_key:
        return ClaudeVLMAnalyzer(api_key=settings.anthropic_api_key, model=settings.anthropic_vlm_model)
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
        return OpenAIChatService(api_key=settings.openai_api_key, model=settings.openai_chat_model)
    if settings.anthropic_api_key:
        return ClaudeChatService(api_key=settings.anthropic_api_key, model=settings.anthropic_chat_model)
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


def _check_requested_model(requested_model: str, *, default_is_openai: bool, default_is_claude: bool) -> None:
    """Shared validation for both resolvers: rejects unknown model names, and
    known ones from a provider this backend isn't configured for (e.g. a
    stored "gpt-4o" choice sent to a Claude-only backend) — with a message
    that tells the user how to fix it from the Settings tab."""
    if requested_model not in _ALLOWED_OPENAI_MODELS | _ALLOWED_CLAUDE_MODELS:
        raise HTTPException(status_code=422, detail=f"Unsupported model '{requested_model}'")
    if requested_model in _ALLOWED_OPENAI_MODELS and not default_is_openai:
        raise HTTPException(
            status_code=422,
            detail=f"Model '{requested_model}' requires an OpenAI-configured backend — choose \"Server default\" in Settings",
        )
    if requested_model in _ALLOWED_CLAUDE_MODELS and not default_is_claude:
        raise HTTPException(
            status_code=422,
            detail=f"Model '{requested_model}' requires an Anthropic-configured backend — choose \"Server default\" in Settings",
        )


def resolve_slide_analyzer(default: SlideAnalyzer, requested_model: str | None) -> SlideAnalyzer:
    """Applies a per-request model override from the extension's Settings
    picker on top of the process-wide default `SlideAnalyzer`.

    Deliberately a plain function, not a second FastAPI dependency: it
    needs the request body's `model` field, which plain `Depends()` can't
    see without duplicating the route's own parameter parsing. Routes call
    this themselves, right after `Depends(get_slide_analyzer)` resolves.

    The `isinstance` checks are also what keep tests safe: `default` is
    always `PlaceholderSlideAnalyzer` under `tests/backend/conftest.py`'s
    dependency override, so this never falls through to constructing a
    real provider client unless one of that provider was already active.
    """
    if not requested_model or requested_model == default.model_name:
        return default
    is_openai = isinstance(default, OpenAIVLMAnalyzer)
    is_claude = isinstance(default, ClaudeVLMAnalyzer)
    _check_requested_model(requested_model, default_is_openai=is_openai, default_is_claude=is_claude)
    settings = get_settings()
    if is_openai:
        return OpenAIVLMAnalyzer(api_key=settings.openai_api_key, model=requested_model)
    return ClaudeVLMAnalyzer(api_key=settings.anthropic_api_key, model=requested_model)


def resolve_chat_service(default: ChatService | None, requested_model: str | None) -> ChatService | None:
    """Mirrors `resolve_slide_analyzer` for chat. `default` may be `None`
    (no provider key configured) — callers must handle that themselves
    before calling this, same as they already do for the un-overridden
    case."""
    if default is None or not requested_model or requested_model == default.model_name:
        return default
    is_openai = isinstance(default, OpenAIChatService)
    is_claude = isinstance(default, ClaudeChatService)
    _check_requested_model(requested_model, default_is_openai=is_openai, default_is_claude=is_claude)
    settings = get_settings()
    if is_openai:
        return OpenAIChatService(api_key=settings.openai_api_key, model=requested_model)
    return ClaudeChatService(api_key=settings.anthropic_api_key, model=requested_model)


async def verify_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Validates the shared local API key (docs/adr/ADR-007: no auth beyond
    a local key). `GET /health` is deliberately exempt from this dependency
    so container healthchecks and basic liveness probing don't need the
    secret — see docker-compose.yml's healthcheck and app/api/v1/health.py.
    """
    settings = get_settings()
    if not settings.local_api_key or x_api_key != settings.local_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing API key")


async def get_current_user(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """Resolves the signed-in user, if any, from `Authorization: Bearer
    <session token>` (docs/PublicHostingMVP.md Phase 2/3). Additive to
    `verify_api_key`, not a replacement — every route below still also
    requires `X-API-Key`.

    No header at all -> `None` ("anonymous"): the unchanged, still fully
    supported local-first flow where nobody has signed in. A header that
    *is* present but names an invalid/expired/malformed token is rejected
    outright with 401 rather than silently treated as anonymous — a
    student who believes they're signed in should never have a capture
    silently attributed to nobody instead of failing loudly.
    """
    if authorization is None:
        return None
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Malformed Authorization header")

    token = authorization.removeprefix("Bearer ").strip()
    session = await SessionRepository(db).get_valid_by_token(token)
    user = await db.get(User, session.user_id) if session is not None else None
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session token")
    return user


async def get_current_user_id(user: User | None = Depends(get_current_user)) -> uuid.UUID | None:
    return user.id if user is not None else None


def is_admin(user: User | None) -> bool:
    """Admins (ADMIN_EMAILS) have no rate limits and may open the admin
    page. The email came from Google's userinfo, and sign-in drops it when
    Google reports it unverified (services/google_oauth.py), so an
    unverified address can never match."""
    return user is not None and user.email is not None and user.email.lower() in get_settings().admin_email_set


async def require_admin(user: User | None = Depends(get_current_user)) -> User:
    if not is_admin(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admins only")
    return user  # type: ignore[return-value]


def ensure_presentation_access(presentation: Presentation, current_user_id: uuid.UUID | None) -> None:
    """Phase 3 (docs/PublicHostingMVP.md): one user's presentations are
    invisible to every other user. Raises 404 — not 403 — so a
    wrong-owner request is indistinguishable from a genuinely unknown id,
    rather than confirming the presentation exists at all.

    A presentation with `user_id is None` (created anonymously, before
    Phase 2 sign-in existed or by a still-not-signed-in request) stays
    open to anyone, preserving the local-first flow exactly as it worked
    before this phase — isolation only applies once a presentation is
    actually owned by someone.
    """
    if presentation.user_id is not None and presentation.user_id != current_user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown presentation_id")


def rate_limit_key(request: Request, current_user_id: uuid.UUID | None) -> str:
    """`"user:<id>"` for a signed-in request, `"ip:<address>"` otherwise —
    see app/models/orm.py's RateLimitEvent docstring for why anonymous
    requests need a key at all (Phase 4's whole point includes a bot
    hitting the API directly, which has no session token).

    `request.client.host` reflects the real client IP, not Render's own
    proxy address, because deploy/hosted/start.sh runs uvicorn with
    `--proxy-headers --forwarded-allow-ips "*"`, which makes Starlette
    trust `X-Forwarded-For` for this field."""
    if current_user_id is not None:
        return f"user:{current_user_id}"
    client_host = request.client.host if request.client else "unknown"
    return f"ip:{client_host}"


async def _record_limit_hit(db: AsyncSession, user: User | None, exc: RateLimitExceeded) -> None:
    """The request's transaction is rolled back when the 429 propagates, so
    the hit is committed on its own first — it is the demand signal the
    admin page shows."""
    await UsageEventRepository(db).record(user_id=user.id if user else None, action=f"limit_hit_{exc.kind}")
    await db.commit()


async def enforce_capture_rate_limit(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user),
) -> None:
    if is_admin(user):
        return
    settings = get_settings()
    repo = RateLimitEventRepository(db)
    try:
        await enforce_rate_limits(
            repo,
            key=rate_limit_key(request, user.id if user else None),
            action="analyze",
            limits=capture_limits(settings, clock.now()),
        )
        await enforce_global_capture_cap(repo, settings)
    except RateLimitExceeded as exc:
        await _record_limit_hit(db, user, exc)
        raise


async def enforce_chat_rate_limit(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user),
) -> None:
    if is_admin(user):
        return
    try:
        await enforce_rate_limits(
            RateLimitEventRepository(db),
            key=rate_limit_key(request, user.id if user else None),
            action="chat",
            limits=chat_limits(get_settings(), clock.now()),
        )
    except RateLimitExceeded as exc:
        await _record_limit_hit(db, user, exc)
        raise
