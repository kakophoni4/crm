"""Document messages.lead_id semantics (nullable, no CHECK).

Revision ID: 0026_messages_lead_id_comment
Revises: 0025_legacy_ownership_phase2
Create Date: 2026-05-17
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0026_messages_lead_id_comment"
down_revision: str | None = "0025_legacy_ownership_phase2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        COMMENT ON COLUMN messages.lead_id IS
        'Optional FK to leads.id for order-scoped thread; '
        'NULL for department-only or legacy rows. '
        'App sets lead_id on inbound/outbound when chat has current_lead_id.';
        """
    )


def downgrade() -> None:
    op.execute("COMMENT ON COLUMN messages.lead_id IS NULL;")
