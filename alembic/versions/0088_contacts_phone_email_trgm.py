"""GIN pg_trgm indexes for contacts phone and email search.

Revision ID: 0088_contacts_phone_email_trgm
Revises: 0087_messages_chat_latest_index
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0088_contacts_phone_email_trgm"
down_revision: str | None = "0087_messages_chat_latest_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_contacts_phone_trgm
        ON contacts USING gin (phone gin_trgm_ops)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_contacts_email_trgm
        ON contacts USING gin (email gin_trgm_ops)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_contacts_email_trgm")
    op.execute("DROP INDEX IF EXISTS idx_contacts_phone_trgm")
