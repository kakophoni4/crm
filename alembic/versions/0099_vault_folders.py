"""Add folders to file_vault_items (parent_id, is_folder, name).

Revision ID: 0099_vault_folders
Revises: 0098_requirements_tasks_client
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0099_vault_folders"
down_revision: str | None = "0098_requirements_tasks_client"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE file_vault_items
            ALTER COLUMN file_id DROP NOT NULL
        """
    )
    op.execute(
        """
        ALTER TABLE file_vault_items
            ADD COLUMN IF NOT EXISTS is_folder BOOLEAN NOT NULL DEFAULT false
        """
    )
    op.execute(
        """
        ALTER TABLE file_vault_items
            ADD COLUMN IF NOT EXISTS parent_id BIGINT NULL
                REFERENCES file_vault_items(id) ON DELETE CASCADE
        """
    )
    op.execute(
        """
        ALTER TABLE file_vault_items
            ADD COLUMN IF NOT EXISTS name TEXT NULL
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_file_vault_owner_parent
            ON file_vault_items (owner_user_id, parent_id)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_file_vault_owner_parent")
    op.execute("ALTER TABLE file_vault_items DROP COLUMN IF EXISTS name")
    op.execute("ALTER TABLE file_vault_items DROP COLUMN IF EXISTS parent_id")
    op.execute("ALTER TABLE file_vault_items DROP COLUMN IF EXISTS is_folder")
    # Do not re-add NOT NULL on file_id — folders may exist.
