"""Add telephony SIP accounts.

Revision ID: 0045_telephony_accounts
Revises: 0044_bots_whatsapp_green
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0045_telephony_accounts"
down_revision = "0044_bots_whatsapp_green"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "telephony_accounts",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False, server_default="bitcall"),
        sa.Column("department_id", sa.BigInteger(), nullable=False),
        sa.Column("group_id", sa.BigInteger(), nullable=True),
        sa.Column("sip_host", sa.Text(), nullable=False),
        sa.Column("sip_port", sa.Integer(), nullable=False, server_default="5060"),
        sa.Column("sip_transport", sa.Text(), nullable=False, server_default="udp"),
        sa.Column("sip_username", sa.Text(), nullable=False),
        sa.Column("sip_password_encrypted", sa.LargeBinary(), nullable=False),
        sa.Column("outbound_caller_id", sa.Text(), nullable=True),
        sa.Column("pbx_extension_prefix", sa.Text(), nullable=True),
        sa.Column("webrtc_ws_url", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(["department_id"], ["departments.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "idx_telephony_accounts_department_id",
        "telephony_accounts",
        ["department_id"],
    )
    op.create_index("idx_telephony_accounts_group_id", "telephony_accounts", ["group_id"])
    op.create_index(
        "idx_telephony_accounts_active",
        "telephony_accounts",
        ["is_active"],
        postgresql_where=sa.text("is_active IS TRUE"),
    )


def downgrade() -> None:
    op.drop_index("idx_telephony_accounts_active", table_name="telephony_accounts")
    op.drop_index("idx_telephony_accounts_group_id", table_name="telephony_accounts")
    op.drop_index("idx_telephony_accounts_department_id", table_name="telephony_accounts")
    op.drop_table("telephony_accounts")
