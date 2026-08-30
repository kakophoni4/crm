"""Share vault folders with a specific CRM user.

Revision ID: 0108_vault_folder_shares
Revises: 0107_large_share_uploads
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0108_vault_folder_shares"
down_revision: str | None = "0107_large_share_uploads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS file_vault_folder_shares (
            id BIGSERIAL PRIMARY KEY,
            folder_id BIGINT NOT NULL REFERENCES file_vault_items(id) ON DELETE CASCADE,
            user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            shared_by BIGINT NULL REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (folder_id, user_id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_file_vault_folder_shares_user_id
        ON file_vault_folder_shares (user_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_file_vault_folder_shares_folder_id
        ON file_vault_folder_shares (folder_id)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_file_vault_folder_shares_folder_id")
    op.execute("DROP INDEX IF EXISTS ix_file_vault_folder_shares_user_id")
    op.execute("DROP TABLE IF EXISTS file_vault_folder_shares")
