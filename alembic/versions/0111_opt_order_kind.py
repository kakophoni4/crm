"""OPT order kind: standard vs benik (beneficiary, no 1C).

Revision ID: 0111_opt_order_kind
Revises: 0110_lavok_parser_favorites
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0111_opt_order_kind"
down_revision: str | None = "0110_lavok_parser_favorites"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE lead_opt_orders
        ADD COLUMN IF NOT EXISTS order_kind TEXT NOT NULL DEFAULT 'standard'
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_lead_opt_orders_order_kind
        ON lead_opt_orders (order_kind)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_lead_opt_orders_order_kind")
    op.execute("ALTER TABLE lead_opt_orders DROP COLUMN IF EXISTS order_kind")
