"""Per-operator chat read state.

Revision ID: 0017_chat_read_state
Revises: 0016_messages_fts_ru
Create Date: 2026-05-17

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0017_chat_read_state"
down_revision: str | None = "0016_messages_fts_ru"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chat_read_state",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("last_read_message_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "read_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["chat_id"], ["chats.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["last_read_message_id"], ["messages.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("user_id", "chat_id"),
    )
    op.create_index("ix_chat_read_state_chat_id", "chat_read_state", ["chat_id"])


def downgrade() -> None:
    op.drop_index("ix_chat_read_state_chat_id", table_name="chat_read_state")
    op.drop_table("chat_read_state")
