"""Set all open leads to pipeline status \"new\".

Revision ID: 0037_reset_open_leads_new
Revises: 0036_simplify_pipeline
"""

from __future__ import annotations

from alembic import op

revision = "0037_reset_open_leads_new"
down_revision = "0036_simplify_pipeline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE leads l
        SET status_id = n.id
        FROM statuses n
        WHERE l.closed_at IS NULL
          AND n.kind = 'lead_pipeline'
          AND n.code = 'new'
        """
    )


def downgrade() -> None:
    pass
