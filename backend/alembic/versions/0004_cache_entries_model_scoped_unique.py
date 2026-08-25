"""cache_entries: scope uniqueness to (image_hash, model_used)

Milestone: extension model picker (gpt-4o / gpt-4o-mini). Previously
`image_hash` alone was unique, so the same slide image analyzed under a
different model would either collide on insert or silently reuse the
wrong model's cached result. This migration drops that single-column
uniqueness and replaces it with a composite constraint so each
(image, model) pair caches independently.

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-25

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Postgres's default name for a single-column `unique=True` constraint
    # created via SQLAlchemy's op.create_table is "<table>_<column>_key".
    op.drop_constraint("cache_entries_image_hash_key", "cache_entries", type_="unique")
    op.create_unique_constraint(
        "uq_cache_entry_image_hash_model_used", "cache_entries", ["image_hash", "model_used"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_cache_entry_image_hash_model_used", "cache_entries", type_="unique")
    op.create_unique_constraint("cache_entries_image_hash_key", "cache_entries", ["image_hash"])
