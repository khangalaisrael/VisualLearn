"""presentations.page_url / lecture_key, slides.created_at

Lets one lecture's captures share a presentation (grouping in "Recent") and
lets retention and ordering use each capture's own date.

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-10

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("presentations", sa.Column("page_url", sa.String(2048), nullable=True))
    op.add_column("presentations", sa.Column("lecture_key", sa.String(512), nullable=True))
    op.create_index("ix_presentations_user_lecture", "presentations", ["user_id", "lecture_key"])
    op.add_column(
        "slides",
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.execute("UPDATE slides SET created_at = analyzed_at WHERE analyzed_at IS NOT NULL")


def downgrade() -> None:
    op.drop_column("slides", "created_at")
    op.drop_index("ix_presentations_user_lecture", table_name="presentations")
    op.drop_column("presentations", "lecture_key")
    op.drop_column("presentations", "page_url")
