"""Admin one-off large file share uploads.

Revision ID: 0107_large_share_uploads
Revises: 0106_bot_referrals
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0107_large_share_uploads"
down_revision: str | None = "0106_bot_referrals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS large_share_uploads (
            id BIGSERIAL PRIMARY KEY,
            owner_user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            storage_key VARCHAR(512) NOT NULL,
            s3_upload_id TEXT NOT NULL,
            original_name VARCHAR(512) NOT NULL,
            mime_type VARCHAR(255) NOT NULL,
            expected_size_bytes BIGINT NOT NULL,
            parent_id BIGINT NULL REFERENCES file_vault_items(id) ON DELETE SET NULL,
            status VARCHAR(32) NOT NULL DEFAULT 'uploading',
            part_etags JSONB NOT NULL DEFAULT '{}'::jsonb,
            expires_in_hours BIGINT NOT NULL DEFAULT 72,
            max_downloads BIGINT NOT NULL DEFAULT 1,
            file_id BIGINT NULL REFERENCES uploaded_files(id) ON DELETE SET NULL,
            vault_item_id BIGINT NULL REFERENCES file_vault_items(id) ON DELETE SET NULL,
            share_id BIGINT NULL REFERENCES file_share_links(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            completed_at TIMESTAMPTZ NULL
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_large_share_uploads_owner_user_id
        ON large_share_uploads (owner_user_id)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_large_share_uploads_owner_user_id")
    op.execute("DROP TABLE IF EXISTS large_share_uploads")
