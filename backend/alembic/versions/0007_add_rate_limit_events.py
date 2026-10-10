"""add rate_limit_events table

docs/PublicHostingMVP.md Phase 4 — per-user/per-IP daily rate limits.
Postgres-backed (see app/models/orm.py's RateLimitEvent docstring for why
Redis isn't the primary store here despite the doc's original "Redis-backed"
phrasing — Upstash isn't actually wired up on the live deployment yet, and
this needs to actually enforce, not degrade gracefully to a no-op).

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-10

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "rate_limit_events",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    # The only query this table ever serves: "how many <action> rows for
    # <key> since <24h ago>" — a composite index on exactly those columns,
    # in that order, is what makes that a fast index range scan instead of
    # a sequential scan as the table grows.
    op.create_index("ix_rate_limit_events_key_action_created_at", "rate_limit_events", ["key", "action", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_rate_limit_events_key_action_created_at", table_name="rate_limit_events")
    op.drop_table("rate_limit_events")
