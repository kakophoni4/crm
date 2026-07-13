"""Add group_senior user role.

Revision ID: 0072_group_senior_role
Revises: 0071_opt_payment_document_ids
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0072_group_senior_role"
down_revision: str | None = "0071_opt_payment_document_ids"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'group_senior'")


def downgrade() -> None:
    # PostgreSQL cannot remove enum values safely.
    pass
