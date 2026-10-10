"""add google sign-in: users.google_sub, sessions table

docs/PublicHostingMVP.md Phase 2 — Google OAuth sign-in. `users.google_sub`
is the OAuth `sub` claim (Google's stable per-account identifier), the
lookup key on sign-in. `sessions` holds the opaque bearer tokens issued
after a successful sign-in (see app/models/orm.py's Session docstring for
why opaque-token-in-a-table rather than a JWT).

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-10

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("google_sub", sa.String(255), nullable=True))
    op.create_unique_constraint("uq_users_google_sub", "users", ["google_sub"])

    op.create_table(
        "sessions",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column("user_id", postgresql.UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    # A single unique index on `token` doubles as the lookup index for
    # get_valid_by_token's WHERE clause, so there's no separate non-unique
    # index needed for it.
    op.create_index("ix_sessions_token", "sessions", ["token"], unique=True)
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.drop_index("ix_sessions_token", table_name="sessions")
    op.drop_table("sessions")
    op.drop_constraint("uq_users_google_sub", "users", type_="unique")
    op.drop_column("users", "google_sub")
