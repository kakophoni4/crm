"""Hide unused lawyer shops from the registry list.

Revision ID: 0112_lawyer_shop_hidden
Revises: 0111_opt_order_kind
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0112_lawyer_shop_hidden"
down_revision: str | None = "0111_opt_order_kind"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE lawyer_shops
        ADD COLUMN IF NOT EXISTS hidden_at TIMESTAMPTZ
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_lawyer_shops_hidden_at
        ON lawyer_shops (hidden_at)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_lawyer_shops_hidden_at")
    op.execute("ALTER TABLE lawyer_shops DROP COLUMN IF EXISTS hidden_at")
