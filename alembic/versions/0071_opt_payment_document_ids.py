"""Multiple payment document attachments per payment.

Revision ID: 0071_opt_payment_document_ids
Revises: 0070_opt_payment_docs_commission_history
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0071_opt_payment_document_ids"
down_revision: str | None = "0070_opt_payment_docs_commission_history"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE lead_opt_order_payments
            ADD COLUMN IF NOT EXISTS document_file_ids JSONB NOT NULL DEFAULT '[]'::jsonb;

        UPDATE lead_opt_order_payments
        SET document_file_ids = jsonb_build_array(document_file_id)
        WHERE document_file_id IS NOT NULL
          AND (
            document_file_ids IS NULL
            OR document_file_ids = '[]'::jsonb
          );
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE lead_opt_order_payments
            DROP COLUMN IF EXISTS document_file_ids;
        """
    )
