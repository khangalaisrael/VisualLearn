"""Repository for the `users` table (docs/PublicHostingMVP.md Phase 2)."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orm import User


class UserRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_google_sub(self, google_sub: str) -> User | None:
        result = await self._db.execute(select(User).where(User.google_sub == google_sub))
        return result.scalar_one_or_none()

    async def get_or_create_by_google_sub(self, google_sub: str, *, email: str | None) -> User:
        """Looks up the user by `google_sub` (stable across sign-ins even if
        the account's email changes); creates one on first sign-in. An
        existing user's email is refreshed to whatever Google reports now,
        so a changed Google account email doesn't go stale here."""
        user = await self.get_by_google_sub(google_sub)
        if user is not None:
            if email is not None and user.email != email:
                user.email = email
                await self._db.flush()
            return user

        user = User(id=uuid.uuid4(), google_sub=google_sub, email=email)
        self._db.add(user)
        await self._db.flush()
        return user
