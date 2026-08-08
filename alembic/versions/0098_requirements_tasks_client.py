"""FNS requirement due/reply fields + task source/unit/new status + task files.

Revision ID: 0098_requirements_tasks_client
Revises: 0097_backfill_contact_owners
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0098_requirements_tasks_client"
down_revision: str | None = "0097_backfill_contact_owners"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE opt_requirements
            ADD COLUMN IF NOT EXISTS response_due_date DATE NULL,
            ADD COLUMN IF NOT EXISTS receipt_due_date DATE NULL,
            ADD COLUMN IF NOT EXISTS reply_status TEXT NOT NULL DEFAULT 'none',
            ADD COLUMN IF NOT EXISTS reply_error TEXT NULL,
            ADD COLUMN IF NOT EXISTS replied_at TIMESTAMP WITHOUT TIME ZONE NULL,
            ADD COLUMN IF NOT EXISTS sbis_requirement_id BIGINT NULL
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_opt_requirements_response_due "
        "ON opt_requirements (response_due_date)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_opt_requirements_reply_status "
        "ON opt_requirements (reply_status)"
    )

    op.execute(
        """
        ALTER TABLE department_tasks
            ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'manual',
            ADD COLUMN IF NOT EXISTS opt_unit_id BIGINT NULL
                REFERENCES opt_units(id) ON DELETE SET NULL,
            ADD COLUMN IF NOT EXISTS opt_requirement_id BIGINT NULL
                REFERENCES opt_requirements(id) ON DELETE SET NULL,
            ADD COLUMN IF NOT EXISTS chat_id BIGINT NULL
                REFERENCES chats(id) ON DELETE SET NULL,
            ADD COLUMN IF NOT EXISTS lead_id BIGINT NULL
                REFERENCES leads(id) ON DELETE SET NULL
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_department_tasks_source "
        "ON department_tasks (source)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_department_tasks_opt_unit "
        "ON department_tasks (opt_unit_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_department_tasks_opt_requirement "
        "ON department_tasks (opt_requirement_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_department_tasks_status "
        "ON department_tasks (status)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS department_task_files (
            id BIGSERIAL PRIMARY KEY,
            task_id BIGINT NOT NULL REFERENCES department_tasks(id) ON DELETE CASCADE,
            file_id BIGINT NOT NULL REFERENCES uploaded_files(id) ON DELETE CASCADE,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
            CONSTRAINT uq_department_task_files_task_file UNIQUE (task_id, file_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_department_task_files_task "
        "ON department_task_files (task_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS department_task_files")
    op.execute("ALTER TABLE department_tasks DROP COLUMN IF EXISTS lead_id")
    op.execute("ALTER TABLE department_tasks DROP COLUMN IF EXISTS chat_id")
    op.execute("ALTER TABLE department_tasks DROP COLUMN IF EXISTS opt_requirement_id")
    op.execute("ALTER TABLE department_tasks DROP COLUMN IF EXISTS opt_unit_id")
    op.execute("ALTER TABLE department_tasks DROP COLUMN IF EXISTS source")
    op.execute("ALTER TABLE opt_requirements DROP COLUMN IF EXISTS sbis_requirement_id")
    op.execute("ALTER TABLE opt_requirements DROP COLUMN IF EXISTS replied_at")
    op.execute("ALTER TABLE opt_requirements DROP COLUMN IF EXISTS reply_error")
    op.execute("ALTER TABLE opt_requirements DROP COLUMN IF EXISTS reply_status")
    op.execute("ALTER TABLE opt_requirements DROP COLUMN IF EXISTS receipt_due_date")
    op.execute("ALTER TABLE opt_requirements DROP COLUMN IF EXISTS response_due_date")
