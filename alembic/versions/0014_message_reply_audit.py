"""Message reply audit and contact group transfers.

Revision ID: 0014_message_reply_audit
Revises: 0013_group_escalation_settings
Create Date: 2026-05-17

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0014_message_reply_audit"
down_revision: str | None = "0013_group_escalation_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE message_reply_audit (
            id BIGSERIAL PRIMARY KEY,
            message_id BIGINT NOT NULL UNIQUE REFERENCES messages(id) ON DELETE CASCADE,
            chat_id BIGINT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
            contact_id BIGINT NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            group_id BIGINT NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
            card_owner_user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            author_user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            is_on_behalf BOOLEAN NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_mra_contact_created
        ON message_reply_audit (contact_id, created_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX idx_mra_card_owner_created
        ON message_reply_audit (card_owner_user_id, created_at DESC)
        """
    )
    op.execute("CREATE INDEX idx_mra_author_user ON message_reply_audit (author_user_id)")

    op.execute(
        """
        CREATE TABLE contact_group_transfers (
            id BIGSERIAL PRIMARY KEY,
            contact_id BIGINT NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            group_id BIGINT NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
            from_user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            to_user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            requested_by BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            state transfer_status NOT NULL,
            senior_user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
            senior_decided_at TIMESTAMPTZ,
            recipient_decided_at TIMESTAMPTZ,
            force_assigned BOOLEAN NOT NULL DEFAULT FALSE,
            comment TEXT,
            expires_at TIMESTAMPTZ NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_cgt_contact_group_state
        ON contact_group_transfers (contact_id, group_id, state)
        """
    )
    op.execute(
        """
        CREATE INDEX idx_cgt_to_user_pending
        ON contact_group_transfers (to_user_id)
        WHERE state IN ('pending_senior', 'pending_recipient', 'pending', 'approved')
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_contact_group_transfers_updated_at
        BEFORE UPDATE ON contact_group_transfers
        FOR EACH ROW
        EXECUTE FUNCTION update_timestamp_trigger()
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_contact_group_transfers_updated_at "
        "ON contact_group_transfers"
    )
    op.execute("DROP TABLE IF EXISTS contact_group_transfers")
    op.execute("DROP TABLE IF EXISTS message_reply_audit")
