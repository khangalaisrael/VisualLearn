"""series table; slides.series_id / subtopic / content_kind

Captures are sorted into topic series (category > series > capture) instead
of only being grouped by the page they came from.

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-11

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "series",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column("user_id", postgresql.UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("category", sa.String(80), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("cover_slide_id", postgresql.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_series_user", "series", ["user_id"])
    op.add_column("slides", sa.Column("series_id", postgresql.UUID(), sa.ForeignKey("series.id"), nullable=True))
    op.add_column("slides", sa.Column("subtopic", sa.String(120), nullable=True))
    op.add_column("slides", sa.Column("content_kind", sa.String(16), nullable=True))
    op.create_index("ix_slides_series", "slides", ["series_id"])


def downgrade() -> None:
    op.drop_index("ix_slides_series", table_name="slides")
    op.drop_column("slides", "content_kind")
    op.drop_column("slides", "subtopic")
    op.drop_column("slides", "series_id")
    op.drop_index("ix_series_user", table_name="series")
    op.drop_table("series")
