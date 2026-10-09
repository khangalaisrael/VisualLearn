"""Shared SQLAlchemy declarative base.

All ORM models (app/models/orm.py) inherit from this so both Alembic
(production migrations against PostgreSQL) and the test suite
(`Base.metadata.create_all()` against SQLite, see tests/backend/conftest.py)
share one metadata object.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
