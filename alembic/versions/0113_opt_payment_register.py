"""OPT payment register fields.

Revision ID: 0113_opt_payment_register
Revises: 0112_lawyer_shop_hidden
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0113_opt_payment_register"
down_revision: str | None = "0112_lawyer_shop_hidden"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE lead_opt_order_lines
          ADD COLUMN comment TEXT,
          ADD COLUMN beneficiary_rate_percent NUMERIC(5, 2),
          ADD COLUMN beneficiary_paid_amount NUMERIC(15, 2) NOT NULL DEFAULT 0;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE lead_opt_order_lines
          DROP COLUMN beneficiary_paid_amount,
          DROP COLUMN beneficiary_rate_percent,
          DROP COLUMN comment;
        """
    )
