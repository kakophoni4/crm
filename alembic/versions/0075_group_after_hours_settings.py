"""Group after-hours auto-reply settings.

Revision ID: 0075_group_after_hours_settings
Revises: 0074_quick_reply_personal
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0075_group_after_hours_settings"
down_revision: str | None = "0074_quick_reply_personal"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DEFAULT_HOURS = (
    '{"mon":[["09:00","18:00"]],"tue":[["09:00","18:00"]],'
    '"wed":[["09:00","18:00"]],"thu":[["09:00","18:00"]],'
    '"fri":[["09:00","18:00"]],"sat":[],"sun":[]}'
)


def upgrade() -> None:
    op.execute(
        f"""
        CREATE TABLE group_after_hours_settings (
            group_id BIGINT PRIMARY KEY REFERENCES groups(id) ON DELETE CASCADE,
            enabled BOOLEAN NOT NULL DEFAULT false,
            reply_text TEXT NOT NULL DEFAULT '',
            delay_minutes INTEGER NOT NULL DEFAULT 15
                CHECK (delay_minutes >= 1 AND delay_minutes <= 1440),
            timezone TEXT NOT NULL DEFAULT 'Europe/Moscow',
            working_hours JSONB NOT NULL DEFAULT '{_DEFAULT_HOURS}'::jsonb,
            cooldown_minutes INTEGER NOT NULL DEFAULT 120
                CHECK (cooldown_minutes >= 0 AND cooldown_minutes <= 10080),
            updated_by BIGINT NULL REFERENCES users(id) ON DELETE SET NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        INSERT INTO group_after_hours_settings (group_id)
        SELECT id FROM groups
        ON CONFLICT (group_id) DO NOTHING
        """
    )
    op.execute(
        """
        ALTER TABLE contact_group_assignments
        ADD COLUMN IF NOT EXISTS after_hours_auto_replied_at TIMESTAMPTZ NULL
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE contact_group_assignments "
        "DROP COLUMN IF EXISTS after_hours_auto_replied_at"
    )
    op.execute("DROP TABLE IF EXISTS group_after_hours_settings")
