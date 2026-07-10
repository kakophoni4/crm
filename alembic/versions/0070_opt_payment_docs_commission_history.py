"""Payment document attachments and commission change history.

Revision ID: 0070_opt_payment_docs_commission_history
Revises: 0069_opt_vat_22_recalc
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0070_opt_payment_docs_commission_history"
down_revision: str | None = "0069_opt_vat_22_recalc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE lead_opt_order_payments
            ADD COLUMN document_file_id BIGINT
                REFERENCES uploaded_files(id) ON DELETE SET NULL;

        CREATE INDEX idx_lead_opt_order_payments_document_file_id
            ON lead_opt_order_payments(document_file_id)
            WHERE document_file_id IS NOT NULL;

        CREATE TABLE lead_opt_order_commission_history (
            id BIGSERIAL PRIMARY KEY,
            order_id BIGINT NOT NULL
                REFERENCES lead_opt_orders(id) ON DELETE CASCADE,
            old_commission_due NUMERIC(15, 2) NOT NULL,
            new_commission_due NUMERIC(15, 2) NOT NULL,
            delta NUMERIC(15, 2) NOT NULL,
            direction TEXT NOT NULL,
            changed_by BIGINT NOT NULL
                REFERENCES users(id) ON DELETE RESTRICT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX idx_lead_opt_order_commission_history_order_id
            ON lead_opt_order_commission_history(order_id);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS lead_opt_order_commission_history")
    op.execute(
        """
        DROP INDEX IF EXISTS idx_lead_opt_order_payments_document_file_id;
        ALTER TABLE lead_opt_order_payments
            DROP COLUMN IF EXISTS document_file_id;
        """
    )
