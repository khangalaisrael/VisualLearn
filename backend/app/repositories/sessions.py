"""Repository for the `sessions` table (docs/PublicHostingMVP.md Phase 2) —
opaque bearer tokens issued after Google sign-in. See app/models/orm.py's
Session docstring for why this is a DB-backed opaque token, not a JWT."""

import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orm import Session

# 30 days: long enough that a student isn't re-prompted to sign in every
# few days mid-semester, short enough that a token leaked once doesn't
# stay valid indefinitely. Revisit once real usage patterns exist.
SESSION_LIFETIME = timedelta(days=30)


class SessionRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(self, user_id: uuid.UUID) -> Session:
        # secrets.token_urlsafe, not uuid4 — this is a credential (anyone
        # holding it can act as this user), and token_urlsafe's 256 bits of
        # CSPRNG output is the standard choice for that, the same way
        # LOCAL_API_KEY itself is generated (see render.yaml's
        # `generateValue: true`), not something a UUID's weaker guarantees
        # (host/time-derived bits in some UUID versions) are meant for.
        token = secrets.token_urlsafe(32)
        session = Session(
            id=uuid.uuid4(),
            user_id=user_id,
            token=token,
            expires_at=datetime.now(timezone.utc) + SESSION_LIFETIME,
        )
        self._db.add(session)
        await self._db.flush()
        return session

    async def get_valid_by_token(self, token: str) -> Session | None:
        result = await self._db.execute(select(Session).where(Session.token == token))
        session = result.scalar_one_or_none()
        if session is None:
            return None
        expires_at = session.expires_at
        if expires_at.tzinfo is None:
            # SQLite (tests/backend/conftest.py) doesn't round-trip
            # timezone-aware datetimes the way Postgres does — a value
            # written as UTC can come back naive. Every write path here
            # stores UTC, so a naive read-back is always implicitly UTC,
            # not the local clock's offset.
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < datetime.now(timezone.utc):
            return None
        return session

    async def delete_by_token(self, token: str) -> None:
        session = await self.get_valid_by_token(token)
        if session is not None:
            await self._db.delete(session)
            await self._db.flush()
