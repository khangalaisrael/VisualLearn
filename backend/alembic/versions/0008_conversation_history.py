"""conversations: slide_id + last_activity_at (chat history, retention)

Recent-chats list and rolling retention both need to know which slide a
chat is about and when it was last used.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-10

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("conversations", sa.Column("slide_id", postgresql.UUID(), sa.ForeignKey("slides.id"), nullable=True))
    op.add_column(
        "conversations",
        sa.Column("last_activity_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    # Existing rows: count retention from when they were created, not from
    # the moment this migration ran.
    op.execute("UPDATE conversations SET last_activity_at = created_at")
    op.create_index("ix_conversations_user_id_last_activity_at", "conversations", ["user_id", "last_activity_at"])


def downgrade() -> None:
    op.drop_index("ix_conversations_user_id_last_activity_at", table_name="conversations")
    op.drop_column("conversations", "last_activity_at")
    op.drop_column("conversations", "slide_id")
