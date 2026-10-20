"""feedback table

A 👍 or 👎 a student gives one answer (a slide summary or a chat reply), with
an optional comment and a copy of the rated text. Signed-out students can
give feedback too, so `user_id` is nullable.

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-20

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "feedback",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column("user_id", postgresql.UUID(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("target", sa.String(8), nullable=False),
        sa.Column("slide_id", postgresql.UUID(), nullable=True),
        sa.Column("message_id", postgresql.UUID(), nullable=True),
        sa.Column("rating", sa.String(4), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("answer_excerpt", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_feedback_created", "feedback", ["created_at"])
    op.create_index("ix_feedback_user", "feedback", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_feedback_user", table_name="feedback")
    op.drop_index("ix_feedback_created", table_name="feedback")
    op.drop_table("feedback")
