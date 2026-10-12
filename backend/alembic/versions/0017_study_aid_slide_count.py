"""study_aids.slide_count

How many slides a study aid was written from, so the panel can say when the
series has grown past it. Null for aids written before this was recorded
(they read at most the newest 12 slides).

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-12

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("study_aids", sa.Column("slide_count", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("study_aids", "slide_count")
