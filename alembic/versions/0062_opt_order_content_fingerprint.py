"""Content fingerprint for OPT order duplicate detection.

Revision ID: 0062_opt_order_content_fingerprint
Revises: 0061_opt_order_source_attachment
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0062_opt_order_content_fingerprint"
down_revision: str | None = "0061_opt_order_source_attachment"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE lead_opt_orders
            ADD COLUMN content_fingerprint TEXT;

        CREATE UNIQUE INDEX uq_lead_opt_orders_content_fingerprint_active
            ON lead_opt_orders (content_fingerprint)
            WHERE content_fingerprint IS NOT NULL
              AND status IN ('queued', 'submitting', 'submitted');
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_lead_opt_orders_content_fingerprint_active")
    op.execute("ALTER TABLE lead_opt_orders DROP COLUMN IF EXISTS content_fingerprint")
