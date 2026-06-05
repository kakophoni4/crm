"""Optimistic version on contact_group_transfers.

Revision ID: 0018_cgt_version
Revises: 0017_chat_read_state
Create Date: 2026-05-17

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0018_cgt_version"
down_revision: str | None = "0017_chat_read_state"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "contact_group_transfers",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )


def downgrade() -> None:
    op.drop_column("contact_group_transfers", "version")
