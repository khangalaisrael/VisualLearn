"""delete captures made before thumbnails existed

Those captures have no picture on any device, so "Recent" showed them as a
blank box. They go for every user, with their chats. One-way: there is
nothing to restore on downgrade.

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-11

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# When local thumbnails shipped (commit 07024c7).
_CUTOFF = "2026-10-10 12:20:00+00"
_OLD_SLIDES = f"SELECT id FROM slides WHERE created_at < TIMESTAMPTZ '{_CUTOFF}'"


def upgrade() -> None:
    op.execute(
        f"DELETE FROM messages WHERE conversation_id IN (SELECT id FROM conversations WHERE slide_id IN ({_OLD_SLIDES}))"
    )
    op.execute(f"DELETE FROM conversations WHERE slide_id IN ({_OLD_SLIDES})")
    op.execute(f"DELETE FROM objects WHERE slide_id IN ({_OLD_SLIDES})")
    op.execute(f"DELETE FROM cache_entries WHERE slide_id IN ({_OLD_SLIDES})")
    op.execute(f"DELETE FROM slides WHERE created_at < TIMESTAMPTZ '{_CUTOFF}'")
    # Lectures left with nothing in them.
    op.execute(
        "DELETE FROM presentations p WHERE NOT EXISTS (SELECT 1 FROM slides s WHERE s.presentation_id = p.id) "
        "AND NOT EXISTS (SELECT 1 FROM conversations c WHERE c.presentation_id = p.id)"
    )


def downgrade() -> None:
    pass
