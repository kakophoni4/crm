"""Chat transfers and takeovers.

Revision ID: 0009_transfers_takeovers
Revises: 0008_chats_messages
Create Date: 2026-05-16

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0009_transfers_takeovers"
down_revision: str | None = "0008_chats_messages"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        for value in ("pending", "approved", "declined"):
            op.execute(f"ALTER TYPE transfer_status ADD VALUE IF NOT EXISTS '{value}'")

    op.execute(
        """
        CREATE TABLE chat_transfers (
            id BIGSERIAL PRIMARY KEY,
            chat_id BIGINT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
            from_user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            to_user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            requested_by BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            status transfer_status NOT NULL,
            reason TEXT,
            approved_by BIGINT REFERENCES users(id) ON DELETE SET NULL,
            approved_at TIMESTAMPTZ,
            accepted_at TIMESTAMPTZ,
            declined_at TIMESTAMPTZ,
            cancelled_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_chat_transfers_chat_status ON chat_transfers (chat_id, status)"
    )
    op.execute(
        "CREATE INDEX idx_chat_transfers_to_user_status ON chat_transfers (to_user_id, status)"
    )
    op.execute(
        "CREATE INDEX idx_chat_transfers_status_created ON chat_transfers (status, created_at)"
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_chat_transfers_chat_active
        ON chat_transfers (chat_id)
        WHERE status IN ('pending', 'approved')
        """
    )

    op.execute(
        """
        CREATE TABLE chat_takeovers (
            id BIGSERIAL PRIMARY KEY,
            chat_id BIGINT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
            senior_user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            released_at TIMESTAMPTZ,
            reason TEXT
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_chat_takeovers_chat_released
        ON chat_takeovers (chat_id, released_at)
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_chat_takeovers_chat_active
        ON chat_takeovers (chat_id)
        WHERE released_at IS NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS chat_takeovers")
    op.execute("DROP TABLE IF EXISTS chat_transfers")
