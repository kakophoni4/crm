"""Add chief_accountant role; migrate existing accountants to chief.

Revision ID: 0084_chief_accountant_role
Revises: 0083_notification_mute_phrases
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0084_chief_accountant_role"
down_revision: str | None = "0083_notification_mute_phrases"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Enum ADD VALUE must run outside a transaction on older Postgres.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'chief_accountant'")

    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_role_org")
    # Existing accountants keep full cabinet access as chief.
    op.execute("UPDATE users SET role = 'chief_accountant' WHERE role = 'accountant'")
    op.execute(
        """
        ALTER TABLE users ADD CONSTRAINT ck_users_role_org CHECK (
            (role = 'user' AND department_id IS NOT NULL)
            OR (role = 'group_senior' AND department_id IS NOT NULL)
            OR (role = 'senior' AND department_id IS NOT NULL AND group_id IS NULL)
            OR (role = 'admin' AND department_id IS NULL AND group_id IS NULL)
            OR (role = 'accountant' AND department_id IS NULL AND group_id IS NULL)
            OR (role = 'chief_accountant' AND department_id IS NULL AND group_id IS NULL)
        )
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_role_org")
    op.execute("UPDATE users SET role = 'accountant' WHERE role = 'chief_accountant'")
    op.execute(
        """
        ALTER TABLE users ADD CONSTRAINT ck_users_role_org CHECK (
            (role = 'user' AND department_id IS NOT NULL)
            OR (role = 'group_senior' AND department_id IS NOT NULL)
            OR (role = 'senior' AND department_id IS NOT NULL AND group_id IS NULL)
            OR (role = 'admin' AND department_id IS NULL AND group_id IS NULL)
            OR (role = 'accountant' AND department_id IS NULL AND group_id IS NULL)
        )
        """
    )
