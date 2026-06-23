"""Add internal WebRTC telephony extensions.

Revision ID: 0046_telephony_extensions
Revises: 0045_telephony_accounts
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0046_telephony_extensions"
down_revision = "0045_telephony_accounts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "telephony_extensions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("extension", sa.Text(), nullable=False),
        sa.Column("password_encrypted", sa.LargeBinary(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["account_id"], ["telephony_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("account_id", "user_id", name="uq_telephony_extensions_account_user"),
        sa.UniqueConstraint(
            "account_id",
            "extension",
            name="uq_telephony_extensions_account_extension",
        ),
    )
    op.create_index(
        "idx_telephony_extensions_account_id",
        "telephony_extensions",
        ["account_id"],
    )
    op.create_index("idx_telephony_extensions_user_id", "telephony_extensions", ["user_id"])
    op.create_index(
        "idx_telephony_extensions_active",
        "telephony_extensions",
        ["is_active"],
        postgresql_where=sa.text("is_active IS TRUE"),
    )


def downgrade() -> None:
    op.drop_index("idx_telephony_extensions_active", table_name="telephony_extensions")
    op.drop_index("idx_telephony_extensions_user_id", table_name="telephony_extensions")
    op.drop_index("idx_telephony_extensions_account_id", table_name="telephony_extensions")
    op.drop_table("telephony_extensions")
