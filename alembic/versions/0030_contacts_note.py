"""Add operator note on contacts.

Revision ID: 0030_contacts_note
Revises: 0029_leads_comment
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0030_contacts_note"
down_revision = "0029_leads_comment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("contacts", sa.Column("note", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("contacts", "note")
