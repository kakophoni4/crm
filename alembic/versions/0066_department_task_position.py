"""Department task kanban position.

Revision ID: 0066_department_task_position
Revises: 0065_accounting_cabinet
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0066_department_task_position"
down_revision: str | None = "0065_accounting_cabinet"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "department_tasks",
        sa.Column("position", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.create_index(
        "ix_department_tasks_status_position",
        "department_tasks",
        ["department_id", "status", "position"],
    )


def downgrade() -> None:
    op.drop_index("ix_department_tasks_status_position", table_name="department_tasks")
    op.drop_column("department_tasks", "position")
