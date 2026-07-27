"""Vacate OPT content_fingerprint on soft-deleted orders.

Revision ID: 0089_opt_fingerprint_soft_delete
Revises: 0088_contacts_phone_email_trgm

Soft-deleted rows kept status queued/submitting/submitted and still occupied
uq_lead_opt_orders_content_fingerprint_active, so re-upload of the same Excel
failed with IntegrityError 500 instead of a clean duplicate message.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0089_opt_fingerprint_soft_delete"
down_revision: str | None = "0088_contacts_phone_email_trgm"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE lead_opt_orders
        SET content_fingerprint = NULL
        WHERE deleted_at IS NOT NULL
          AND content_fingerprint IS NOT NULL
        """
    )
    op.execute("DROP INDEX IF EXISTS uq_lead_opt_orders_content_fingerprint_active")
    op.execute(
        """
        CREATE UNIQUE INDEX uq_lead_opt_orders_content_fingerprint_active
            ON lead_opt_orders (content_fingerprint)
            WHERE content_fingerprint IS NOT NULL
              AND deleted_at IS NULL
              AND status IN ('queued', 'submitting', 'submitted')
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_lead_opt_orders_content_fingerprint_active")
    op.execute(
        """
        CREATE UNIQUE INDEX uq_lead_opt_orders_content_fingerprint_active
            ON lead_opt_orders (content_fingerprint)
            WHERE content_fingerprint IS NOT NULL
              AND status IN ('queued', 'submitting', 'submitted')
        """
    )
