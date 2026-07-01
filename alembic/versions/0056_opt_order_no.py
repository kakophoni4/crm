"""Sequential application number per lead (Сделка 254 → Заявка 1, 2, …).

Revision ID: 0056_opt_order_no
Revises: 0055_bot_service_types
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0056_opt_order_no"
down_revision: str | None = "0055_bot_service_types"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE lead_opt_orders ADD COLUMN order_no INT;

        WITH numbered AS (
            SELECT
                id,
                ROW_NUMBER() OVER (
                    PARTITION BY lead_id ORDER BY created_at ASC, id ASC
                )::INT AS seq
            FROM lead_opt_orders
        )
        UPDATE lead_opt_orders o
        SET order_no = numbered.seq
        FROM numbered
        WHERE o.id = numbered.id;

        ALTER TABLE lead_opt_orders ALTER COLUMN order_no SET NOT NULL;

        CREATE UNIQUE INDEX uq_lead_opt_orders_lead_order_no
            ON lead_opt_orders (lead_id, order_no);
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_lead_opt_orders_lead_order_no")
    op.execute("ALTER TABLE lead_opt_orders DROP COLUMN IF EXISTS order_no")
