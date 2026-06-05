"""GIN pg_trgm indexes for global search (contacts + chat preview).

Revision ID: 0024_pg_trgm_search
Revises: 0023_chat_transfers_deprecated
Create Date: 2026-05-17
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0024_pg_trgm_search"
down_revision: str | None = "0023_chat_transfers_deprecated"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        """
        CREATE INDEX idx_contacts_full_name_trgm
        ON contacts USING gin (full_name gin_trgm_ops)
        """
    )
    op.execute(
        """
        CREATE INDEX idx_contacts_telegram_username_trgm
        ON contacts USING gin (telegram_username gin_trgm_ops)
        """
    )
    op.execute(
        """
        CREATE INDEX idx_chats_last_message_preview_trgm
        ON chats USING gin (last_message_preview gin_trgm_ops)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_chats_last_message_preview_trgm")
    op.execute("DROP INDEX IF EXISTS idx_contacts_telegram_username_trgm")
    op.execute("DROP INDEX IF EXISTS idx_contacts_full_name_trgm")
