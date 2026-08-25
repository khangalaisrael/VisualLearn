"""objects: add language column (code-object detection)

Milestone: code-object detection. A "code" object type is being added
alongside the existing equation/`latex` pattern — `language` is the
programming-language equivalent of `latex`, only populated for `code`
objects, null otherwise.

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-25

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("objects", sa.Column("language", sa.String(32), nullable=True))


def downgrade() -> None:
    op.drop_column("objects", "language")
