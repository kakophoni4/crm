"""Composite index for per-chat latest message lookup.

Revision ID: 0087_messages_chat_latest_index
Revises: 0086_opt_order_no_soft_delete_unique
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0087_messages_chat_latest_index"
down_revision: str | None = "0086_opt_order_no_soft_delete_unique"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Supports LATERAL / DISTINCT ON latest-message per chat_id.
    op.create_index(
        "ix_messages_chat_id_created_at_id",
        "messages",
        ["chat_id", sa.text("created_at DESC"), sa.text("id DESC")],
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_messages_chat_id_created_at_id",
        table_name="messages",
        if_exists=True,
    )
