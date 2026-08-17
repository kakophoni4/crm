"""Idle contract banner admin toggle.

Revision ID: 0102_idle_banner_settings
Revises: 0101_task_collaborators_parent
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0102_idle_banner_settings"
down_revision: str | None = "0101_task_collaborators_parent"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS idle_banner_settings (
            id SMALLINT PRIMARY KEY,
            is_enabled BOOLEAN NOT NULL DEFAULT false,
            updated_by BIGINT NULL REFERENCES users(id) ON DELETE SET NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        INSERT INTO idle_banner_settings (id, is_enabled)
        VALUES (1, false)
        ON CONFLICT (id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS idle_banner_settings")
