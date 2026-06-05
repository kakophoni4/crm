"""Backfill lead_comments rows from leads.comment where missing.

Revision ID: 0034_lead_comment_backfill
Revises: 0033_lead_comments_group_id
"""

from __future__ import annotations

from alembic import op

revision = "0034_lead_comment_backfill"
down_revision = "0033_lead_comments_group_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO lead_comments (lead_id, group_id, body, created_by, created_at)
        SELECT l.id, l.group_id, trim(l.comment), NULL, l.updated_at
        FROM leads l
        WHERE l.comment IS NOT NULL
          AND trim(l.comment) <> ''
          AND NOT EXISTS (
            SELECT 1
            FROM lead_comments lc
            WHERE lc.lead_id = l.id
              AND lc.body = trim(l.comment)
          )
        """,
    )


def downgrade() -> None:
    pass
