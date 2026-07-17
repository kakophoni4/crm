"""Global staff-notification mute phrases on bot settings.

Revision ID: 0083_notification_mute_phrases
Revises: 0082_opt_unit_periods
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0083_notification_mute_phrases"
down_revision: str | None = "0082_opt_unit_periods"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE notification_bot_settings
        ADD COLUMN IF NOT EXISTS mute_phrases JSONB NOT NULL DEFAULT '[]'::jsonb
        """
    )
    op.execute(
        """
        DELETE FROM staff_notification_events
        WHERE status = 'cancelled'
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE notification_bot_settings DROP COLUMN IF EXISTS mute_phrases"
    )
