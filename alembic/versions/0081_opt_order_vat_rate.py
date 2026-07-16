"""Store VAT rate percent on OPT orders (20 or 22).

Revision ID: 0081_opt_order_vat_rate
Revises: 0080_cga_bot_default_owner_source
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0081_opt_order_vat_rate"
down_revision: str | None = "0080_cga_bot_default_owner_source"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE lead_opt_orders
        ADD COLUMN IF NOT EXISTS vat_rate_percent numeric(5, 2) NOT NULL DEFAULT 22
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE lead_opt_orders DROP COLUMN IF EXISTS vat_rate_percent")
