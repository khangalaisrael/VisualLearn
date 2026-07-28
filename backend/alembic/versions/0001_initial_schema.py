"""initial schema: users, presentations, slides

Sprint 1 scope only (docs/ROADMAP.md, Milestone 1). The remaining tables in
docs/DATA_MODEL.md (objects, embeddings, conversations, messages,
cache_entries) are added in later migrations, each alongside the milestone
that first needs it.

Revision ID: 0001
Revises:
Create Date: 2026-07-18

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "presentations",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column("user_id", postgresql.UUID(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "slides",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column("presentation_id", postgresql.UUID(), sa.ForeignKey("presentations.id"), nullable=False),
        sa.Column("slide_number", sa.Integer(), nullable=False),
        sa.Column("image_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("presentation_id", "image_hash", name="uq_slide_presentation_image_hash"),
    )
    op.create_index("ix_slides_presentation_id", "slides", ["presentation_id"])


def downgrade() -> None:
    op.drop_index("ix_slides_presentation_id", table_name="slides")
    op.drop_table("slides")
    op.drop_table("presentations")
    op.drop_table("users")
