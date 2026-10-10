"""Admin dashboard data: GET /admin/overview, /admin/users, /admin/waitlist.

Read-only, for the owner only. `require_admin` needs a signed-in session
whose verified Google email is in ADMIN_EMAILS; everyone else gets 403, on
top of the shared API key every route needs.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin, verify_api_key
from app.core import clock
from app.core.config import get_settings
from app.db.session import get_db
from app.models.schemas import AdminOverview, AdminUsersResponse, AdminWaitlistResponse
from app.services import admin_stats

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(verify_api_key), Depends(require_admin)])


@router.get("/overview", response_model=AdminOverview)
async def overview(db: AsyncSession = Depends(get_db)) -> AdminOverview:
    return await admin_stats.build_overview(db, get_settings(), clock.now())


@router.get("/users", response_model=AdminUsersResponse)
async def users(db: AsyncSession = Depends(get_db)) -> AdminUsersResponse:
    return await admin_stats.build_users(db, clock.now())


@router.get("/waitlist", response_model=AdminWaitlistResponse)
async def waitlist(db: AsyncSession = Depends(get_db)) -> AdminWaitlistResponse:
    return await admin_stats.build_waitlist(db)
