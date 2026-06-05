"""Bot events inbox and outbound log tables.

Revision ID: 0011_bot_events_outbound
Revises: 0010_bots
Create Date: 2026-05-16

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0011_bot_events_outbound"
down_revision: str | None = "0010_bots"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE bot_events_inbox (
            id BIGSERIAL PRIMARY KEY,
            bot_id BIGINT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
            event_id TEXT NOT NULL,
            received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            processed_at TIMESTAMPTZ,
            payload JSONB NOT NULL,
            signature TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'received',
            last_error TEXT,
            CONSTRAINT uq_bot_events_inbox_event_id UNIQUE (event_id),
            CONSTRAINT chk_bot_events_inbox_status
                CHECK (status IN ('received', 'processing', 'done', 'failed'))
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_bot_events_inbox_bot_received
        ON bot_events_inbox (bot_id, received_at DESC)
        """
    )
    op.execute("CREATE INDEX idx_bot_events_inbox_status ON bot_events_inbox (status)")

    op.execute(
        """
        CREATE TABLE bot_outbound_log (
            id BIGSERIAL PRIMARY KEY,
            bot_id BIGINT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
            request_id TEXT NOT NULL,
            command TEXT NOT NULL,
            payload JSONB NOT NULL,
            status bot_outbound_status NOT NULL DEFAULT 'queued',
            attempts INT NOT NULL DEFAULT 0,
            last_attempt_at TIMESTAMPTZ,
            last_error TEXT,
            response_payload JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_bot_outbound_log_request_id UNIQUE (request_id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_bot_outbound_log_bot_created
        ON bot_outbound_log (bot_id, created_at DESC)
        """
    )
    op.execute("CREATE INDEX idx_bot_outbound_log_status ON bot_outbound_log (status)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS bot_outbound_log")
    op.execute("DROP TABLE IF EXISTS bot_events_inbox")
