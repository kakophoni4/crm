"""Add audit_action values for lead lifecycle.

Revision ID: 0020_lead_audit
Revises: 0019_leads
Create Date: 2026-05-17

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0020_lead_audit"
down_revision: str | None = "0019_leads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        for action in ("lead.close", "lead.status.update"):
            op.execute(f"ALTER TYPE audit_action ADD VALUE IF NOT EXISTS '{action}'")


def downgrade() -> None:
    pass
