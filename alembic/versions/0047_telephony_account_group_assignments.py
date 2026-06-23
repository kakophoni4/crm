"""Telephony account group assignments.

Revision ID: 0047_telephony_account_groups
Revises: 0046_telephony_extensions
"""

from __future__ import annotations

from alembic import op

revision = "0047_telephony_account_groups"
down_revision = "0046_telephony_extensions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE telephony_account_group_assignments (
            account_id BIGINT NOT NULL REFERENCES telephony_accounts(id) ON DELETE CASCADE,
            group_id BIGINT NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (account_id, group_id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_telephony_account_group_assignments_group_id
        ON telephony_account_group_assignments (group_id)
        """
    )
    op.execute(
        """
        INSERT INTO telephony_account_group_assignments (account_id, group_id)
        SELECT id, group_id
        FROM telephony_accounts
        WHERE group_id IS NOT NULL
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS telephony_account_group_assignments")
