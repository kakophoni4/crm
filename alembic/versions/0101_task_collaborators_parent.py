"""Task collaborators, parent/follow-up link.

Revision ID: 0101_task_collaborators_parent
Revises: 0100_tree_prices_task_comments
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0101_task_collaborators_parent"
down_revision: str | None = "0100_tree_prices_task_comments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE department_tasks
            ADD COLUMN IF NOT EXISTS parent_task_id BIGINT NULL
                REFERENCES department_tasks(id) ON DELETE SET NULL
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_department_tasks_parent_task_id
            ON department_tasks (parent_task_id)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS department_task_collaborators (
            task_id BIGINT NOT NULL REFERENCES department_tasks(id) ON DELETE CASCADE,
            user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            added_by BIGINT NULL REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (task_id, user_id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_department_task_collaborators_user_id
            ON department_task_collaborators (user_id)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS department_task_collaborators")
    op.execute("ALTER TABLE department_tasks DROP COLUMN IF EXISTS parent_task_id")
