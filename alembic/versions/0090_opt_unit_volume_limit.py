"""Add volume_limit to opt_units for accountant caps.

Revision ID: 0090_opt_unit_volume_limit
Revises: 0089_opt_fingerprint_soft_delete
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0090_opt_unit_volume_limit"
down_revision: str | None = "0089_opt_fingerprint_soft_delete"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE opt_units
            ADD COLUMN IF NOT EXISTS volume_limit NUMERIC(18, 2) NULL
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE opt_units DROP COLUMN IF EXISTS volume_limit")
