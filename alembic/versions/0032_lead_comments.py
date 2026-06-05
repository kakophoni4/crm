"""Lead comment history (operator notes per order).

Revision ID: 0032_lead_comments
Revises: 0031_contact_status_returning
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0032_lead_comments"
down_revision = "0031_contact_status_returning"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lead_comments",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("lead_id", sa.BigInteger(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_lead_comments_lead_created",
        "lead_comments",
        ["lead_id", "created_at"],
    )
    op.execute(
        """
        INSERT INTO lead_comments (lead_id, body, created_by, created_at)
        SELECT l.id, trim(l.comment), NULL, l.updated_at
        FROM leads l
        WHERE l.comment IS NOT NULL AND trim(l.comment) <> ''
        """,
    )


def downgrade() -> None:
    op.drop_index("idx_lead_comments_lead_created", table_name="lead_comments")
    op.drop_table("lead_comments")
