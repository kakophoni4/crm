"""Mark legacy chat_transfers as deprecated (phase-2 prep, non-destructive).

Revision ID: 0023_chat_transfers_deprecated
Revises: 0022_leads_list_index
Create Date: 2026-05-17

Does not RENAME or DROP — runtime legacy routes are already 410. Full archive/DROP
after LEGACY_OWNERSHIP phase 2 (see docs/LEGACY_OWNERSHIP_REMOVAL.md).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0023_chat_transfers_deprecated"
down_revision: str | None = "0022_leads_list_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        COMMENT ON TABLE chat_transfers IS
        'DEPRECATED (ownership v2): read-only archive. '
        'Use contact_group_transfers. '
        'DROP or RENAME to chat_transfers_archived after phase-2 checklist.';
        """
    )


def downgrade() -> None:
    op.execute("COMMENT ON TABLE chat_transfers IS NULL")
