"""Add comment column to leads.

Revision ID: 0029_leads_comment
Revises: 0028_chat_workflow_answered
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0029_leads_comment"
down_revision = "0028_chat_workflow_answered"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("comment", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("leads", "comment")
