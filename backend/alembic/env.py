"""Alembic environment — async, targets PostgreSQL (docker-compose.yml).

The test suite does NOT go through Alembic; it builds the schema directly
from `Base.metadata` against SQLite (tests/backend/conftest.py), which is
why this file's migrations (alembic/versions/) use PostgreSQL-specific
column types explicitly rather than the ORM's cross-dialect GUID type.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.db.base import Base
from app.db.url import normalize_database_url
from app.models import orm  # noqa: F401  (registers models on Base.metadata)

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Same normalization as app/db/session.py, so a hosted provider's URL
# (e.g. Neon's ?sslmode=require) works for migrations too.
_database_url, _connect_args = normalize_database_url(get_settings().database_url)
# ConfigParser treats % as interpolation — escape it (URL-encoded passwords).
config.set_main_option("sqlalchemy.url", _database_url.replace("%", "%%"))

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = create_async_engine(_database_url, poolclass=pool.NullPool, connect_args=_connect_args)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
