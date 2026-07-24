"""Free soft-deleted OPT order_no; partial unique on active rows.

Revision ID: 0086_opt_order_no_soft_delete_unique
Revises: 0085_opt_order_soft_delete
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0086_opt_order_no_soft_delete_unique"
down_revision: str | None = "0085_opt_order_soft_delete"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Soft-deleted rows kept their old order_no and blocked renumber/create
    # (uq_lead_opt_orders_lead_order_no). Move them out of the positive range.
    op.execute(
        """
        UPDATE lead_opt_orders
        SET order_no = -id
        WHERE deleted_at IS NOT NULL
          AND order_no > 0
        """
    )
    op.execute("DROP INDEX IF EXISTS uq_lead_opt_orders_lead_order_no")
    op.execute(
        """
        CREATE UNIQUE INDEX uq_lead_opt_orders_lead_order_no
            ON lead_opt_orders (lead_id, order_no)
            WHERE deleted_at IS NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_lead_opt_orders_lead_order_no")
    # Ensure no duplicate (lead_id, order_no) among all rows before full unique.
    op.execute(
        """
        UPDATE lead_opt_orders
        SET order_no = -id
        WHERE deleted_at IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_lead_opt_orders_lead_order_no
            ON lead_opt_orders (lead_id, order_no)
        """
    )
