"""Add returning value to contact_status enum.

Revision ID: 0031_contact_status_returning
Revises: 0030_contacts_note
"""

from __future__ import annotations

from alembic import op

revision = "0031_contact_status_returning"
down_revision = "0030_contacts_note"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE contact_status ADD VALUE IF NOT EXISTS 'returning'")


def downgrade() -> None:
    pass
