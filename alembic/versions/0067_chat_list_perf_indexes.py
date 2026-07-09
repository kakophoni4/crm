"""Performance indexes for chat list and latest-message lookup.

Revision ID: 0067_chat_list_perf_indexes
Revises: 0066_department_task_position
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0067_chat_list_perf_indexes"
down_revision: str | None = "0066_department_task_position"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Speeds up max(id) per chat_id (latest message subquery) via index-only scan.
    op.create_index(
        "ix_messages_chat_id_id",
        "messages",
        ["chat_id", "id"],
        if_not_exists=True,
    )
    # Speeds up chat list ordering (last_message_at DESC NULLS LAST, id DESC).
    op.create_index(
        "ix_chats_last_message_at_id",
        "chats",
        [sa.text("last_message_at DESC NULLS LAST"), sa.text("id DESC")],
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("ix_chats_last_message_at_id", table_name="chats", if_exists=True)
    op.drop_index("ix_messages_chat_id_id", table_name="messages", if_exists=True)
