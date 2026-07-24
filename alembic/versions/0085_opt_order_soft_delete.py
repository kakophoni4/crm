"""Soft-delete for OPT orders: deleted_at / deleted_by / delete_snapshot.

Revision ID: 0085_opt_order_soft_delete
Revises: 0084_chief_accountant_role
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0085_opt_order_soft_delete"
down_revision: str | None = "0084_chief_accountant_role"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "lead_opt_orders",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "lead_opt_orders",
        sa.Column("deleted_by", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "lead_opt_orders",
        sa.Column(
            "delete_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_lead_opt_orders_deleted_by_users",
        "lead_opt_orders",
        "users",
        ["deleted_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "idx_lead_opt_orders_deleted_at",
        "lead_opt_orders",
        ["deleted_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_lead_opt_orders_deleted_at", table_name="lead_opt_orders")
    op.drop_constraint(
        "fk_lead_opt_orders_deleted_by_users",
        "lead_opt_orders",
        type_="foreignkey",
    )
    op.drop_column("lead_opt_orders", "delete_snapshot")
    op.drop_column("lead_opt_orders", "deleted_by")
    op.drop_column("lead_opt_orders", "deleted_at")
