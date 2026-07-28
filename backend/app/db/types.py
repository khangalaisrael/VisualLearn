"""Platform-independent UUID column type.

Renders as PostgreSQL's native UUID type in production and as a
32-character hex CHAR column on every other backend. This is the canonical
"Backend-agnostic GUID Type" recipe from the SQLAlchemy documentation.

The only reason this project needs it: it lets the ORM models in
app/models/orm.py run unmodified against SQLite in-memory for fast unit
tests (tests/backend/conftest.py) while using PostgreSQL's native UUID type
for real deployments (docker-compose.yml). Production migrations
(backend/alembic/versions/) target PostgreSQL directly and are not affected
by this — they declare `postgresql.UUID` explicitly.
"""

import uuid

from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.types import CHAR, TypeDecorator


class GUID(TypeDecorator):
    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID())
        return dialect.type_descriptor(CHAR(32))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return str(value)
        if not isinstance(value, uuid.UUID):
            return "%.32x" % uuid.UUID(value).int
        return "%.32x" % value.int

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if not isinstance(value, uuid.UUID):
            value = uuid.UUID(value)
        return value
