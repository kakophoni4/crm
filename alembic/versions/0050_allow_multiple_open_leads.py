from __future__ import annotations

from alembic import op

revision = "0050_allow_multiple_open_leads"
down_revision = "0049_quick_reply_templates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_leads_open_contact_group")


def downgrade() -> None:
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_leads_open_contact_group
        ON leads (contact_id, group_id)
        WHERE closed_at IS NULL
        """
    )
