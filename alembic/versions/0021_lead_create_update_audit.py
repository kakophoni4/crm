"""Add audit_action values for manual lead create and field updates.

Revision ID: 0021_lead_create_update_audit
Revises: 0020_lead_audit
Create Date: 2026-05-17

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0021_lead_create_update_audit"
down_revision: str | None = "0020_lead_audit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        for action in ("lead.create", "lead.update"):
            op.execute(f"ALTER TYPE audit_action ADD VALUE IF NOT EXISTS '{action}'")


def downgrade() -> None:
    pass
