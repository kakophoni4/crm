"""Personal quick reply templates + relax shared-only scope check.

Revision ID: 0074_quick_reply_personal
Revises: 0073_group_senior_role_org_check
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0074_quick_reply_personal"
down_revision: str | None = "0073_group_senior_role_org_check"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE quick_reply_templates
        ADD COLUMN IF NOT EXISTS owner_user_id BIGINT
        REFERENCES users(id) ON DELETE CASCADE
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_quick_reply_templates_owner "
        "ON quick_reply_templates (owner_user_id)"
    )
    op.execute("ALTER TABLE quick_reply_templates DROP CONSTRAINT IF EXISTS ck_quick_reply_scope")
    op.execute(
        """
        ALTER TABLE quick_reply_templates
        ADD CONSTRAINT ck_quick_reply_scope CHECK (
            (
                owner_user_id IS NOT NULL
                AND department_id IS NULL
                AND group_id IS NULL
            )
            OR (
                owner_user_id IS NULL
                AND (department_id IS NOT NULL OR group_id IS NOT NULL)
            )
        )
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE quick_reply_templates DROP CONSTRAINT IF EXISTS ck_quick_reply_scope")
    op.execute(
        """
        DELETE FROM quick_reply_templates
        WHERE owner_user_id IS NOT NULL
        """
    )
    op.execute("ALTER TABLE quick_reply_templates DROP COLUMN IF EXISTS owner_user_id")
    op.execute(
        """
        ALTER TABLE quick_reply_templates
        ADD CONSTRAINT ck_quick_reply_scope
        CHECK (department_id IS NOT NULL OR group_id IS NOT NULL)
        """
    )
