"""Phase-2 legacy ownership: archive chat_transfers, drop assignee cols, unread_count_user.

Revision ID: 0025_legacy_ownership_phase2
Revises: 0024_pg_trgm_search
Create Date: 2026-05-17

Safe path: RENAME chat_transfers (not DROP) — historical rows retained for audit.
contacts.assigned_user_id / assigned_group_id dropped after ownership v2 backfill (0012).
chats.last_handled_by_user_id kept (ORM Chat.assigned_user_id).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0025_legacy_ownership_phase2"
down_revision: str | None = "0024_pg_trgm_search"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ARCHIVED_TRANSFERS = "chat_transfers_archived_2026"


def upgrade() -> None:
    # 1) Archive legacy chat_transfers (COUNT>0 safe — rename preserves rows).
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'chat_transfers'
            ) THEN
                ALTER TABLE chat_transfers RENAME TO {_ARCHIVED_TRANSFERS};
            END IF;
        END $$;
        """
    )

    # 2) Drop deprecated contact-level assignee columns (canonical: contact_group_assignments).
    op.execute("DROP INDEX IF EXISTS idx_contacts_assigned_user_id")
    op.execute("DROP INDEX IF EXISTS idx_contacts_assigned_group_id")
    op.execute("ALTER TABLE contacts DROP COLUMN IF EXISTS assigned_user_id")
    op.execute("ALTER TABLE contacts DROP COLUMN IF EXISTS assigned_group_id")

    # 3) Drop global unread counter (canonical: chat_read_state / unread_for_me).
    op.execute("ALTER TABLE chats DROP COLUMN IF EXISTS unread_count_user")


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE chats
        ADD COLUMN IF NOT EXISTS unread_count_user INT NOT NULL DEFAULT 0
        """
    )

    op.execute(
        """
        ALTER TABLE contacts
        ADD COLUMN IF NOT EXISTS assigned_user_id BIGINT
            REFERENCES users(id) ON DELETE SET NULL
        """
    )
    op.execute(
        """
        ALTER TABLE contacts
        ADD COLUMN IF NOT EXISTS assigned_group_id BIGINT
            REFERENCES groups(id) ON DELETE SET NULL
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_contacts_assigned_user_id ON contacts (assigned_user_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_contacts_assigned_group_id ON contacts (assigned_group_id)"
    )

    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = '{_ARCHIVED_TRANSFERS}'
            ) AND NOT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'chat_transfers'
            ) THEN
                ALTER TABLE {_ARCHIVED_TRANSFERS} RENAME TO chat_transfers;
            END IF;
        END $$;
        """
    )
