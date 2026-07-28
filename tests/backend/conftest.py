"""Shared pytest fixtures for the backend test suite.

Uses an in-memory SQLite database (via the ORM's cross-dialect GUID type,
app/db/types.py) instead of a real PostgreSQL instance, so `pytest` runs
fast and requires no Docker. `alembic upgrade head` is only exercised
against the real stack — see backend/README.md.
"""

from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.deps import get_chat_service, get_slide_analyzer
from app.core.cache import get_redis
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.schemas import ChatUsage
from app.services.chat_service import ChatChunk
from app.services.slide_analyzer import PlaceholderSlideAnalyzer

TEST_DATABASE_URL = "sqlite+aiosqlite://"


class FakeRedis:
    """In-memory stand-in for redis.asyncio.Redis.

    Backs the two operations app/services/cache_service.py actually uses
    (get/set with an `ex` TTL, which this fake ignores — tests don't run
    long enough for TTL expiry to matter) plus `ping` for the health check.
    """

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def ping(self) -> bool:
        return True

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        del ex
        self._store[key] = value


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)

    async with session_factory() as session:
        yield session

    await engine.dispose()


class FakeChatService:
    """Stand-in for ChatService used by every test via the `client` fixture
    below — guarantees tests never call a real provider API regardless of
    whether OPENAI_API_KEY/ANTHROPIC_API_KEY happen to be set in whatever
    environment `pytest` runs in (mirrors PlaceholderSlideAnalyzer's role
    for get_slide_analyzer)."""

    model_name = "fake-chat-model"

    async def stream_chat(self, *, system_prompt: str, message: str, effort: str):
        del system_prompt, message, effort
        yield ChatChunk(delta="Fake ", done=False)
        yield ChatChunk(delta="answer.", done=False)
        yield ChatChunk(delta=None, done=True, usage=ChatUsage(input_tokens=10, output_tokens=2, cache_read_input_tokens=0))


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    # One shared instance per test, not one per dependency resolution — the
    # analysis cache must actually persist across the multiple requests a
    # single test might make (e.g. upload the same image twice).
    fake_redis = FakeRedis()

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    async def override_get_redis() -> FakeRedis:
        return fake_redis

    async def override_get_slide_analyzer() -> PlaceholderSlideAnalyzer:
        # Tests must never call the real Claude API — override unconditionally
        # rather than relying on ANTHROPIC_API_KEY being unset in whatever
        # environment `pytest` happens to run in (see app/api/deps.py).
        return PlaceholderSlideAnalyzer()

    async def override_get_chat_service() -> FakeChatService:
        return FakeChatService()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = override_get_redis
    app.dependency_overrides[get_slide_analyzer] = override_get_slide_analyzer
    app.dependency_overrides[get_chat_service] = override_get_chat_service

    settings = get_settings()
    settings.local_api_key = "test-api-key"
    settings.max_upload_bytes = 8 * 1024 * 1024

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
