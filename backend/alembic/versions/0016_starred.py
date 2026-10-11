"""series.starred, notes.starred

A user can mark a series or a note as a favourite; favourites are listed first.

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-11

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("series", sa.Column("starred", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("notes", sa.Column("starred", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("notes", "starred")
    op.drop_column("series", "starred")
