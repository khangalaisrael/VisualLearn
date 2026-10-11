"""notes table

Study notes a signed-in user saves from an answer or writes themselves. Not
covered by the 30-day retention: a note stays until its owner deletes it.

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-11

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notes",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column("user_id", postgresql.UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("series_id", postgresql.UUID(), nullable=True),
        sa.Column("slide_id", postgresql.UUID(), nullable=True),
        sa.Column("topic", sa.String(120), nullable=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("source", sa.String(8), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_notes_user_updated", "notes", ["user_id", "updated_at"])


def downgrade() -> None:
    op.drop_index("ix_notes_user_updated", table_name="notes")
    op.drop_table("notes")
