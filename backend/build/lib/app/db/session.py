"""Async database session management.

`get_db` is the FastAPI dependency every router uses (see
docs/ARCHITECTURE.md §4: "api (routers) -> services -> repositories -> db").
Tests override this dependency directly via `app.dependency_overrides`
(see tests/backend/conftest.py) rather than swapping the DATABASE_URL, which
keeps the override explicit and avoids import-order surprises.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

_settings = get_settings()

engine = create_async_engine(_settings.database_url, echo=False, pool_pre_ping=True)

AsyncSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
