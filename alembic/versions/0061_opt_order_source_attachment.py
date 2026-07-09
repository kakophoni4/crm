"""Link OPT orders to source chat attachment for idempotent upload.

Revision ID: 0061_opt_order_source_attachment
Revises: 0060_department_tasks
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0061_opt_order_source_attachment"
down_revision: str | None = "0060_department_tasks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE lead_opt_orders
            ADD COLUMN source_message_id BIGINT REFERENCES messages(id) ON DELETE SET NULL,
            ADD COLUMN source_attachment_index INT;

        CREATE UNIQUE INDEX uq_lead_opt_orders_source_attachment
            ON lead_opt_orders (source_message_id, source_attachment_index)
            WHERE source_message_id IS NOT NULL AND source_attachment_index IS NOT NULL;
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_lead_opt_orders_source_attachment")
    op.execute(
        """
        ALTER TABLE lead_opt_orders
            DROP COLUMN IF EXISTS source_attachment_index,
            DROP COLUMN IF EXISTS source_message_id;
        """
    )
