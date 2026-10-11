"""quizzes and quiz_attempts tables

Multiple-choice quizzes written from a series' slides, and the runs through
them. Both expire with the 30-day retention.

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-11

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "quizzes",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column("user_id", postgresql.UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("series_id", postgresql.UUID(), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("questions", sa.JSON(), nullable=False),
        sa.Column("resources", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_quizzes_user_series", "quizzes", ["user_id", "series_id"])
    op.create_table(
        "quiz_attempts",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column("quiz_id", postgresql.UUID(), sa.ForeignKey("quizzes.id"), nullable=False),
        sa.Column("answers", sa.JSON(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_quiz_attempts_quiz", "quiz_attempts", ["quiz_id"])


def downgrade() -> None:
    op.drop_index("ix_quiz_attempts_quiz", table_name="quiz_attempts")
    op.drop_table("quiz_attempts")
    op.drop_index("ix_quizzes_user_series", table_name="quizzes")
    op.drop_table("quizzes")
