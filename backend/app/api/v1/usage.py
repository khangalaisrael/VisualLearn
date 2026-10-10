"""GET /usage (what the extension's quiet counter shows) and POST /waitlist
(the "Join the Pro waitlist" button).

/usage is read-only: it counts with the same windows the limiter enforces
but never records anything, so polling it cannot consume anyone's quota.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, is_admin, is_email_allowed, rate_limit_key, verify_api_key
from app.core import clock
from app.core.config import get_settings
from app.db.session import get_db
from app.models.orm import User
from app.models.schemas import UsageResponse, UsageWindow, WaitlistRequest, WaitlistResponse
from app.repositories.rate_limit_events import RateLimitEventRepository
from app.repositories.usage_events import ProWaitlistRepository
from app.services.rate_limiter import Limit, capture_limits, chat_limits, day_window

router = APIRouter(tags=["usage"], dependencies=[Depends(verify_api_key)])


async def _window(repo: RateLimitEventRepository, key: str, action: str, limit: Limit) -> UsageWindow:
    return UsageWindow(
        used=await repo.count_since(key, action, limit.since),
        limit=limit.maximum,
        resets_at=limit.resets_at,
    )


@router.get("/usage", response_model=UsageResponse)
async def get_usage(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user),
) -> UsageResponse:
    settings = get_settings()
    at = clock.now()
    repo = RateLimitEventRepository(db)
    key = rate_limit_key(request, user.id if user else None)
    signed_in = user is not None
    daily, monthly = capture_limits(settings, at, signed_in=signed_in)
    (chat_daily,) = chat_limits(settings, at, signed_in=signed_in)
    admin = is_admin(user)

    day_start, _ = day_window(at, settings.rate_limit_timezone)
    global_blocked = (
        not admin and await repo.count_all_since("analyze", day_start) >= settings.global_captures_per_day
    )
    return UsageResponse(
        signed_in=user is not None,
        is_admin=admin,
        unlimited=admin,
        captures_today=await _window(repo, key, "analyze", daily),
        captures_month=await _window(repo, key, "analyze", monthly),
        chat_today=await _window(repo, key, "chat", chat_daily),
        global_blocked=global_blocked,
        invite_only=settings.invite_only,
        allowed=is_email_allowed(user.email if user else None),
        invite_contact=settings.privacy_contact_email,
    )


@router.post("/waitlist", response_model=WaitlistResponse)
async def join_pro_waitlist(
    body: WaitlistRequest,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user),
) -> WaitlistResponse:
    """Signed-in only: the point is being able to email the person later, so
    an anonymous click would be a number with nobody behind it."""
    if user is None:
        raise HTTPException(status_code=401, detail="Sign in to join the Pro waitlist.")
    await ProWaitlistRepository(db).record_click(uuid.UUID(str(user.id)), body.source)
    await db.commit()
    return WaitlistResponse(joined=True)
