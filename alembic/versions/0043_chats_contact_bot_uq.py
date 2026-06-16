"""One open chat per (contact, bot) instead of per contact only.

Revision ID: 0043_chats_contact_bot_uq
Revises: 0042_user_group_memberships
"""

from __future__ import annotations

from alembic import op

revision = "0043_chats_contact_bot_uq"
down_revision = "0042_user_group_memberships"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_chats_contact_active")
    op.execute(
        """
        CREATE UNIQUE INDEX uq_chats_contact_bot_active
        ON chats (contact_id, bot_id)
        WHERE status != 'archived'
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_chats_contact_bot_active")
    op.execute(
        """
        CREATE UNIQUE INDEX uq_chats_contact_active
        ON chats (contact_id)
        WHERE status != 'archived'
        """
    )
