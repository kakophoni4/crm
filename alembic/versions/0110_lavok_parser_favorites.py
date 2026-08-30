"""Favorite flag for lavok parser lots.

Revision ID: 0110_lavok_parser_favorites
Revises: 0109_lawyer_registry
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0110_lavok_parser_favorites"
down_revision: str | None = "0109_lawyer_registry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE lavok_parser_lots
        ADD COLUMN IF NOT EXISTS is_favorite BOOLEAN NOT NULL DEFAULT false
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_lavok_parser_lots_is_favorite
        ON lavok_parser_lots (is_favorite)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_lavok_parser_lots_is_favorite")
    op.execute("ALTER TABLE lavok_parser_lots DROP COLUMN IF EXISTS is_favorite")
