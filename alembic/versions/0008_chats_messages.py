"""Chats and messages tables.

Revision ID: 0008_chats_messages
Revises: 0007_statuses
Create Date: 2026-05-16

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0008_chats_messages"
down_revision: str | None = "0007_statuses"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE chat_status ADD VALUE IF NOT EXISTS 'in_progress'")
        op.execute("ALTER TYPE message_direction ADD VALUE IF NOT EXISTS 'inbound'")
        op.execute("ALTER TYPE message_direction ADD VALUE IF NOT EXISTS 'outbound'")
        op.execute("ALTER TYPE message_kind ADD VALUE IF NOT EXISTS 'image'")
        op.execute("ALTER TYPE message_kind ADD VALUE IF NOT EXISTS 'voice'")
        op.execute("ALTER TYPE message_kind ADD VALUE IF NOT EXISTS 'document'")
        for action in (
            "chat.create",
            "chat.status.update",
            "chat.archive",
            "chat.message.send",
            "chat.transfer.accept",
            "chat.transfer.cancel",
            "chat.transfer.force",
            "chat.takeover.release",
        ):
            op.execute(f"ALTER TYPE audit_action ADD VALUE IF NOT EXISTS '{action}'")

    op.execute(
        """
        CREATE TABLE chats (
            id BIGSERIAL PRIMARY KEY,
            contact_id BIGINT NOT NULL REFERENCES contacts(id) ON DELETE RESTRICT,
            bot_id BIGINT NULL,
            assigned_user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
            assigned_group_id BIGINT REFERENCES groups(id) ON DELETE SET NULL,
            assigned_department_id BIGINT REFERENCES departments(id) ON DELETE SET NULL,
            status chat_status NOT NULL DEFAULT 'open',
            status_id BIGINT REFERENCES statuses(id) ON DELETE SET NULL,
            last_message_at TIMESTAMPTZ,
            last_message_preview TEXT,
            unread_count_user INT NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT chk_chats_last_message_preview_len
                CHECK (last_message_preview IS NULL OR char_length(last_message_preview) <= 200)
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_chats_contact_active
        ON chats (contact_id)
        WHERE status != 'archived'
        """
    )
    op.execute(
        "CREATE INDEX idx_chats_assigned_user_status ON chats (assigned_user_id, status)"
    )
    op.execute(
        "CREATE INDEX idx_chats_assigned_group_status ON chats (assigned_group_id, status)"
    )
    op.execute(
        """
        CREATE INDEX idx_chats_assigned_department_status
        ON chats (assigned_department_id, status)
        """
    )
    op.execute("CREATE INDEX idx_chats_contact_id ON chats (contact_id)")
    op.execute(
        "CREATE INDEX idx_chats_last_message_at ON chats (last_message_at DESC NULLS LAST)"
    )

    op.execute(
        """
        CREATE TRIGGER trg_chats_updated_at
        BEFORE UPDATE ON chats
        FOR EACH ROW
        EXECUTE FUNCTION update_timestamp_trigger()
        """
    )

    op.execute(
        """
        CREATE TABLE messages (
            id BIGSERIAL PRIMARY KEY,
            chat_id BIGINT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
            direction message_direction NOT NULL,
            kind message_kind NOT NULL,
            text TEXT,
            attachments JSONB NOT NULL DEFAULT '[]'::jsonb,
            sender_user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
            external_message_id TEXT,
            external_event_id TEXT,
            reply_to_message_id BIGINT REFERENCES messages(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            idempotency_key TEXT UNIQUE
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_messages_chat_created
        ON messages (chat_id, created_at DESC)
        """
    )
    op.execute("CREATE INDEX idx_messages_attachments ON messages USING GIN (attachments)")
    op.execute(
        """
        CREATE UNIQUE INDEX uq_messages_external_event_id
        ON messages (external_event_id)
        WHERE external_event_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_chats_updated_at ON chats")
    op.execute("DROP TABLE IF EXISTS messages")
    op.execute("DROP TABLE IF EXISTS chats")
