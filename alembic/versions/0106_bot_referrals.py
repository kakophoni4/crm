"""Optional per-bot Telegram referrals.

Revision ID: 0106_bot_referrals
Revises: 0105_lawyer_parser_cabinet
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0106_bot_referrals"
down_revision: str | None = "0105_lawyer_parser_cabinet"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE bots
        ADD COLUMN IF NOT EXISTS referrals_enabled BOOLEAN NOT NULL DEFAULT false
        """
    )
    op.execute(
        """
        ALTER TABLE bots
        ADD COLUMN IF NOT EXISTS telegram_username TEXT NULL
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS contact_referral_codes (
            id BIGSERIAL PRIMARY KEY,
            contact_id BIGINT NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            bot_id BIGINT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
            code TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (contact_id, bot_id),
            UNIQUE (code)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS contact_referrals (
            id BIGSERIAL PRIMARY KEY,
            bot_id BIGINT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
            referrer_contact_id BIGINT NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            referred_contact_id BIGINT NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            code TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (bot_id, referred_contact_id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_contact_referrals_referrer
        ON contact_referrals (referrer_contact_id, bot_id)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_contact_referrals_referrer")
    op.execute("DROP TABLE IF EXISTS contact_referrals")
    op.execute("DROP TABLE IF EXISTS contact_referral_codes")
    op.execute("ALTER TABLE bots DROP COLUMN IF EXISTS telegram_username")
    op.execute("ALTER TABLE bots DROP COLUMN IF EXISTS referrals_enabled")
