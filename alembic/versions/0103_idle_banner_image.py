"""Idle banner custom image.

Revision ID: 0103_idle_banner_image
Revises: 0102_idle_banner_settings
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0103_idle_banner_image"
down_revision: str | None = "0102_idle_banner_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE idle_banner_settings
            ADD COLUMN IF NOT EXISTS image_file_id BIGINT NULL
                REFERENCES uploaded_files(id) ON DELETE SET NULL
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE idle_banner_settings DROP COLUMN IF EXISTS image_file_id")
