"""Add group_id to lead_comments for per-group visibility.

Revision ID: 0033_lead_comments_group_id
Revises: 0032_lead_comments
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0033_lead_comments_group_id"
down_revision = "0032_lead_comments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "lead_comments",
        sa.Column("group_id", sa.BigInteger(), nullable=True),
    )
    op.execute(
        """
        UPDATE lead_comments lc
        SET group_id = l.group_id
        FROM leads l
        WHERE l.id = lc.lead_id
        """,
    )
    op.alter_column("lead_comments", "group_id", nullable=False)
    op.create_foreign_key(
        "fk_lead_comments_group_id",
        "lead_comments",
        "groups",
        ["group_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("idx_lead_comments_group_created", "lead_comments", ["group_id", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_lead_comments_group_created", table_name="lead_comments")
    op.drop_constraint("fk_lead_comments_group_id", "lead_comments", type_="foreignkey")
    op.drop_column("lead_comments", "group_id")
