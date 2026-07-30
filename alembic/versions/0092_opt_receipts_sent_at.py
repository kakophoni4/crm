"""Add receipts_sent_at to lead_opt_orders.

Revision ID: 0092_opt_receipts_sent_at
Revises: 0091_opt_receipts
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0092_opt_receipts_sent_at"
down_revision: str | None = "0091_opt_receipts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE lead_opt_orders
            ADD COLUMN IF NOT EXISTS receipts_sent_at TIMESTAMP WITHOUT TIME ZONE NULL
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE lead_opt_orders DROP COLUMN IF EXISTS receipts_sent_at")
