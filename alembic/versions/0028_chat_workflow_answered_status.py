"""Rename chat workflow status in_progress -> answered.

Revision ID: 0028
Revises: 0027
"""

from __future__ import annotations

from alembic import op

revision = "0028_chat_workflow_answered"
down_revision = "0027_add_username_to_users"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE statuses
        SET code = 'answered', label = 'Отвечен'
        WHERE code = 'in_progress' AND kind = 'chat_label'
        """
    )
    op.execute(
        """
        INSERT INTO statuses (code, kind, label, color, sort_order, is_active)
        SELECT 'answered', 'chat_label', 'Отвечен', '#F39C12', 2, true
        WHERE NOT EXISTS (
            SELECT 1 FROM statuses WHERE code = 'answered' AND kind = 'chat_label'
        )
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE statuses
        SET code = 'in_progress', label = 'В работе'
        WHERE code = 'answered' AND kind = 'chat_label'
        """
    )
