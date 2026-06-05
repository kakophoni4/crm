"""Bots table with encrypted secrets.

Revision ID: 0010_bots
Revises: 0009_transfers_takeovers
Create Date: 2026-05-16

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0010_bots"
down_revision: str | None = "0009_transfers_takeovers"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE bots (
            id BIGSERIAL PRIMARY KEY,
            code TEXT NOT NULL,
            name TEXT NOT NULL,
            owner_type bot_owner_type NOT NULL,
            owner_id BIGINT NOT NULL,
            inbound_secret_encrypted BYTEA NOT NULL,
            outbound_secret_encrypted BYTEA NOT NULL,
            outbound_url TEXT NOT NULL,
            health_url TEXT,
            ip_allowlist INET[],
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            last_seen_at TIMESTAMPTZ,
            last_health_status TEXT,
            last_health_checked_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_bots_code UNIQUE (code)
        )
        """
    )
    op.execute("CREATE INDEX idx_bots_owner ON bots (owner_type, owner_id)")
    op.execute("CREATE INDEX idx_bots_is_active ON bots (is_active)")
    op.execute(
        """
        CREATE TRIGGER trg_bots_updated_at
        BEFORE UPDATE ON bots
        FOR EACH ROW
        EXECUTE FUNCTION update_timestamp_trigger()
        """
    )
    op.execute(
        """
        ALTER TABLE chats
        ADD CONSTRAINT fk_chats_bot_id
        FOREIGN KEY (bot_id) REFERENCES bots(id) ON DELETE SET NULL
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE chats DROP CONSTRAINT IF EXISTS fk_chats_bot_id")
    op.execute("DROP TRIGGER IF EXISTS trg_bots_updated_at ON bots")
    op.execute("DROP TABLE IF EXISTS bots")
