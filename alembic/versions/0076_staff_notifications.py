"""Staff Telegram notification bot.

Revision ID: 0076_staff_notifications
Revises: 0075_group_after_hours_settings
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0076_staff_notifications"
down_revision: str | None = "0075_group_after_hours_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE staff_notification_kind AS ENUM (
                'inbound_message',
                'new_card',
                'escalation_group_senior',
                'escalation_dept_senior',
                'escalation_admin'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
        """
    )
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE staff_notification_status AS ENUM (
                'sent',
                'acked',
                'cancelled',
                'failed'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS notification_bot_settings (
            id SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
            bot_token_encrypted BYTEA NULL,
            bot_username TEXT NULL,
            webhook_secret TEXT NULL,
            is_enabled BOOLEAN NOT NULL DEFAULT false,
            updated_by BIGINT NULL REFERENCES users(id) ON DELETE SET NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        INSERT INTO notification_bot_settings (id)
        VALUES (1)
        ON CONFLICT (id) DO NOTHING
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_telegram_links (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            telegram_user_id BIGINT NOT NULL,
            telegram_username TEXT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_user_telegram_links_tg UNIQUE (telegram_user_id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_user_telegram_links_user_id
        ON user_telegram_links (user_id)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_notification_settings (
            user_id BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            group_senior_timeout_minutes INTEGER NOT NULL DEFAULT 15
                CHECK (group_senior_timeout_minutes >= 1 AND group_senior_timeout_minutes <= 1440),
            mute_phrases JSONB NOT NULL DEFAULT '[]'::jsonb,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        ALTER TABLE contact_group_assignments
        ADD COLUMN IF NOT EXISTS staff_notify_acked_at TIMESTAMPTZ NULL,
        ADD COLUMN IF NOT EXISTS staff_notify_acked_by BIGINT NULL
            REFERENCES users(id) ON DELETE SET NULL,
        ADD COLUMN IF NOT EXISTS staff_notify_group_senior_at TIMESTAMPTZ NULL,
        ADD COLUMN IF NOT EXISTS staff_notify_dept_senior_at TIMESTAMPTZ NULL,
        ADD COLUMN IF NOT EXISTS staff_notify_admin_at TIMESTAMPTZ NULL
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS staff_notification_events (
            id BIGSERIAL PRIMARY KEY,
            kind staff_notification_kind NOT NULL,
            status staff_notification_status NOT NULL DEFAULT 'sent',
            contact_id BIGINT NULL REFERENCES contacts(id) ON DELETE SET NULL,
            chat_id BIGINT NULL REFERENCES chats(id) ON DELETE SET NULL,
            group_id BIGINT NULL REFERENCES groups(id) ON DELETE SET NULL,
            department_id BIGINT NULL REFERENCES departments(id) ON DELETE SET NULL,
            target_user_id BIGINT NULL REFERENCES users(id) ON DELETE SET NULL,
            telegram_user_id BIGINT NULL,
            telegram_message_id BIGINT NULL,
            pending_key BIGINT NULL,
            contact_name TEXT NULL,
            body_text TEXT NULL,
            error_text TEXT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            acked_at TIMESTAMPTZ NULL,
            cancelled_at TIMESTAMPTZ NULL
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_staff_notif_events_created
        ON staff_notification_events (created_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_staff_notif_events_target
        ON staff_notification_events (target_user_id, created_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_staff_notif_events_pending
        ON staff_notification_events (contact_id, group_id, pending_key)
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_staff_notif_cycle_target_kind
        ON staff_notification_events (
            contact_id, group_id, pending_key, target_user_id, kind, telegram_user_id
        )
        WHERE pending_key IS NOT NULL AND target_user_id IS NOT NULL AND telegram_user_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS staff_notification_events")
    op.execute(
        """
        ALTER TABLE contact_group_assignments
        DROP COLUMN IF EXISTS staff_notify_acked_at,
        DROP COLUMN IF EXISTS staff_notify_acked_by,
        DROP COLUMN IF EXISTS staff_notify_group_senior_at,
        DROP COLUMN IF EXISTS staff_notify_dept_senior_at,
        DROP COLUMN IF EXISTS staff_notify_admin_at
        """
    )
    op.execute("DROP TABLE IF EXISTS user_notification_settings")
    op.execute("DROP TABLE IF EXISTS user_telegram_links")
    op.execute("DROP TABLE IF EXISTS notification_bot_settings")
    op.execute("DROP TYPE IF EXISTS staff_notification_status")
    op.execute("DROP TYPE IF EXISTS staff_notification_kind")
