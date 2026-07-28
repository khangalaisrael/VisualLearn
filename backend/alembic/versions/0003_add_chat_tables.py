"""add objects, conversations, messages (Milestone 3 chat, docs/DATA_MODEL.md §2)

`objects.graph_structure` is a deviation from the original DATA_MODEL.md
draft (written before ADR-010) — added here since `SlideObject` already
carries it and Figure-mode chat context should be able to include it.

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-18

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "objects",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column("slide_id", postgresql.UUID(), sa.ForeignKey("slides.id"), nullable=False),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("bounding_box", postgresql.JSONB(), nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("latex", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("graph_structure", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_objects_slide_id", "objects", ["slide_id"])

    op.create_table(
        "conversations",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column("presentation_id", postgresql.UUID(), sa.ForeignKey("presentations.id"), nullable=True),
        sa.Column("user_id", postgresql.UUID(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column("conversation_id", postgresql.UUID(), sa.ForeignKey("conversations.id"), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("query_mode", sa.String(16), nullable=False),
        sa.Column("referenced_object_ids", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_messages_conversation_id_created_at", "messages", ["conversation_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_messages_conversation_id_created_at", table_name="messages")
    op.drop_table("messages")
    op.drop_table("conversations")
    op.drop_index("ix_objects_slide_id", table_name="objects")
    op.drop_table("objects")
