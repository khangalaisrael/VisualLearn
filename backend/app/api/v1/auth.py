"""POST /auth/google, POST /auth/logout — docs/PublicHostingMVP.md Phase 2.

Still behind `verify_api_key` like every other endpoint (docs/API_CONTRACT.md
§1: the `Authorization: Bearer <session token>` this phase introduces is
additive to `X-API-Key`, not a replacement for it) — signing in doesn't
bypass the existing shared-secret gate, it layers per-user identity on top
of it. Nothing elsewhere in the API requires the bearer token yet; scoping
existing endpoints by the signed-in user is Phase 3, not this one.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id, invite_only_error, is_email_allowed, verify_api_key
from app.db.session import get_db
from app.models.schemas import AuthResponse, GoogleAuthRequest, LogoutRequest
from app.repositories.sessions import SessionRepository
from app.repositories.users import UserRepository
from app.services.account import delete_account
from app.services.google_oauth import GoogleTokenVerificationError, verify_google_access_token

router = APIRouter(tags=["auth"], dependencies=[Depends(verify_api_key)])


@router.post("/auth/google", response_model=AuthResponse)
async def sign_in_with_google(request: GoogleAuthRequest, db: AsyncSession = Depends(get_db)) -> AuthResponse:
    try:
        google_user = await verify_google_access_token(request.access_token)
    except GoogleTokenVerificationError as exc:
        raise HTTPException(status_code=401, detail="Could not verify Google sign-in.") from exc

    # Invite-only mode: an account that isn't on the list never gets a user or a session.
    if not is_email_allowed(google_user.email):
        raise invite_only_error()

    user = await UserRepository(db).get_or_create_by_google_sub(google_user.sub, email=google_user.email)
    session = await SessionRepository(db).create(user.id)
    await db.commit()

    return AuthResponse(session_token=session.token, email=user.email)


@router.post("/auth/logout", status_code=204)
async def logout(request: LogoutRequest, db: AsyncSession = Depends(get_db)) -> None:
    await SessionRepository(db).delete_by_token(request.session_token)
    await db.commit()


@router.delete("/auth/account", status_code=204)
async def delete_my_account(
    db: AsyncSession = Depends(get_db),
    current_user_id: uuid.UUID | None = Depends(get_current_user_id),
) -> None:
    """Deletes the signed-in user and all of their chats, captures and
    sessions. Irreversible; the extension asks for confirmation first."""
    if current_user_id is None:
        raise HTTPException(status_code=401, detail="Sign in to delete your account.")
    await delete_account(db, current_user_id)
