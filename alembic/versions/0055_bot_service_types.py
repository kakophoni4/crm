"""Per-bot allowed lead service types (Деревья / ОПТ).

Revision ID: 0055_bot_service_types
Revises: 0054_lead_opt_orders
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0055_bot_service_types"
down_revision: str | None = "0054_lead_opt_orders"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE bots
        ADD COLUMN service_types TEXT[] NOT NULL
        DEFAULT ARRAY['Деревья', 'ОПТ']::TEXT[]
        """
    )
    op.execute(
        """
        UPDATE bots
        SET service_types = ARRAY['Деревья', 'ОПТ']::TEXT[]
        WHERE service_types IS NULL OR cardinality(service_types) = 0
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE bots DROP COLUMN IF EXISTS service_types")
