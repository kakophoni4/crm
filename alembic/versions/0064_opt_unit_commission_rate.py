"""Per-lavka commission rate override from park spreadsheet.

Revision ID: 0064_opt_unit_commission_rate
Revises: 0063_opt_commission_adjustment
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0064_opt_unit_commission_rate"
down_revision: str | None = "0063_opt_commission_adjustment"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE opt_units
            ADD COLUMN commission_rate_percent NUMERIC(5, 2);
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE opt_units DROP COLUMN IF EXISTS commission_rate_percent")
