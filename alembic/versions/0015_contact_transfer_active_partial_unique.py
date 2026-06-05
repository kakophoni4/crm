"""Prepare DB-level active-transfer uniqueness.

Revision ID: 0015_cgt_active_uq
Revises: 0014_message_reply_audit
Create Date: 2026-05-17

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0015_cgt_active_uq"
down_revision: str | None = "0014_message_reply_audit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_cgt_active_contact_group
        ON contact_group_transfers (contact_id, group_id)
        WHERE state IN ('pending_senior', 'pending_recipient', 'pending', 'approved')
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_cgt_active_contact_group")
