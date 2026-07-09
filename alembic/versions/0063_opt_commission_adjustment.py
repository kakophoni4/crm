"""Manual commission adjustment for OPT orders (discounts / penalties).

Revision ID: 0063_opt_commission_adjustment
Revises: 0062_opt_order_content_fingerprint
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0063_opt_commission_adjustment"
down_revision: str | None = "0062_opt_order_content_fingerprint"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE lead_opt_orders
            ADD COLUMN commission_adjustment NUMERIC(15, 2) NOT NULL DEFAULT 0;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE lead_opt_orders
            DROP COLUMN IF EXISTS commission_adjustment;
        """
    )
