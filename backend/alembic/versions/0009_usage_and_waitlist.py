"""usage_events, pro_waitlist_clicks, global-cap index

Per-action usage/cost records for the admin view, the "Join the Pro
waitlist" click log, and an (action, created_at) index so the global daily
cap can count every user's captures without a sequential scan.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-10

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "usage_events",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column("user_id", postgresql.UUID(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("model", sa.String(64), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cache_hit", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("est_cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("slide_id", postgresql.UUID(), nullable=True),
        sa.Column("conversation_id", postgresql.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_usage_events_created_at", "usage_events", ["created_at"])
    op.create_index("ix_usage_events_user_id_created_at", "usage_events", ["user_id", "created_at"])

    op.create_table(
        "pro_waitlist_clicks",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column("user_id", postgresql.UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_pro_waitlist_clicks_user_id", "pro_waitlist_clicks", ["user_id"])

    op.create_index("ix_rate_limit_events_action_created_at", "rate_limit_events", ["action", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_rate_limit_events_action_created_at", table_name="rate_limit_events")
    op.drop_index("ix_pro_waitlist_clicks_user_id", table_name="pro_waitlist_clicks")
    op.drop_table("pro_waitlist_clicks")
    op.drop_index("ix_usage_events_user_id_created_at", table_name="usage_events")
    op.drop_index("ix_usage_events_created_at", table_name="usage_events")
    op.drop_table("usage_events")
