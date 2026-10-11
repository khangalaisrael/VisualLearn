"""study_aids table

A study guide, a cheat sheet and a deck of flashcards per series, written
from its slides. They expire with the 30-day retention, like quizzes.

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-11

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "study_aids",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column("user_id", postgresql.UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("series_id", postgresql.UUID(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("progress", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_study_aids_user_series", "study_aids", ["user_id", "series_id"])


def downgrade() -> None:
    op.drop_index("ix_study_aids_user_series", table_name="study_aids")
    op.drop_table("study_aids")
