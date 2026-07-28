"""add cache_entries (Milestone 2 analysis cache, docs/ARCHITECTURE.md §5)

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-18

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cache_entries",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column("image_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("slide_id", postgresql.UUID(), sa.ForeignKey("slides.id"), nullable=True),
        sa.Column("analysis_result", postgresql.JSONB(), nullable=False),
        sa.Column("model_used", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("cache_entries")
