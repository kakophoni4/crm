"""Russian FTS on messages.text for chat search.

Revision ID: 0016_messages_fts_ru
Revises: 0015_cgt_active_uq
Create Date: 2026-05-17

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0016_messages_fts_ru"
down_revision: str | None = "0015_cgt_active_uq"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE messages
        ADD COLUMN search_vector tsvector
        GENERATED ALWAYS AS (
            to_tsvector('russian', coalesce(text, ''))
        ) STORED
        """
    )
    op.execute(
        """
        CREATE INDEX idx_messages_search_vector
        ON messages USING GIN (search_vector)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_messages_search_vector")
    op.execute("ALTER TABLE messages DROP COLUMN IF EXISTS search_vector")
