"""Index for contact-scoped lead list pagination.

Revision ID: 0022_leads_list_index
Revises: 0021_lead_create_update_audit
Create Date: 2026-05-17

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0022_leads_list_index"
down_revision: str | None = "0021_lead_create_update_audit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX idx_leads_contact_created_id
        ON leads (contact_id, created_at DESC, id DESC)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_leads_contact_created_id")
