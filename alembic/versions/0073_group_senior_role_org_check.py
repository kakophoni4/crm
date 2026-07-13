"""Allow group_senior and accountant in ck_users_role_org.

Revision ID: 0073_group_senior_role_org_check
Revises: 0072_group_senior_role
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0073_group_senior_role_org_check"
down_revision: str | None = "0072_group_senior_role"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE users DROP CONSTRAINT ck_users_role_org")
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


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP CONSTRAINT ck_users_role_org")
    op.execute(
        """
        ALTER TABLE users ADD CONSTRAINT ck_users_role_org CHECK (
            (role = 'user' AND department_id IS NOT NULL)
            OR (role = 'senior' AND department_id IS NOT NULL AND group_id IS NULL)
            OR (role = 'admin' AND department_id IS NULL AND group_id IS NULL)
        )
        """
    )
