"""Mark SBIS correction receipts separately from filing pack.

Revision ID: 0094_opt_receipts_is_correction
Revises: 0093_opt_round_commission_rubles
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0094_opt_receipts_is_correction"
down_revision: str | None = "0093_opt_round_commission_rubles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE opt_receipts
            ADD COLUMN IF NOT EXISTS is_correction BOOLEAN NOT NULL DEFAULT false
        """
    )
    op.execute(
        """
        UPDATE opt_receipts
        SET is_correction = true
        WHERE is_correction = false
          AND (
            source_filename ILIKE '%корректир%'
            OR source_filename ILIKE '%уточненн%'
            OR source_filename ILIKE '%уточнённ%'
            OR source_filename ILIKE '%корректирующ%'
          )
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE opt_receipts DROP COLUMN IF EXISTS is_correction")
