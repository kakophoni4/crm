"""Add audit_action values for department task history.

Revision ID: 0104_task_audit_actions
Revises: 0103_idle_banner_image
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0104_task_audit_actions"
down_revision: str | None = "0103_idle_banner_image"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        for action in (
            "task.create",
            "task.update",
            "task.handoff",
            "task.status.update",
            "task.delete",
        ):
            op.execute(f"ALTER TYPE audit_action ADD VALUE IF NOT EXISTS '{action}'")


def downgrade() -> None:
    pass
