"""File vault, share links, and group chat file library.

Revision ID: 0059_file_storage
Revises: 0058_opt_buyers
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0059_file_storage"
down_revision: str | None = "0058_opt_buyers"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "uploaded_files",
        "uploaded_by",
        existing_type=sa.BigInteger(),
        nullable=True,
    )

    op.create_table(
        "file_vault_items",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("file_id", sa.BigInteger(), nullable=False),
        sa.Column("owner_user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["file_id"], ["uploaded_files.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("file_id", name="uq_file_vault_items_file_id"),
    )
    op.create_index(
        "ix_file_vault_items_owner_user_id",
        "file_vault_items",
        ["owner_user_id"],
    )

    op.create_table(
        "file_share_links",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("file_id", sa.BigInteger(), nullable=False),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("is_anonymous", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("max_downloads", sa.Integer(), nullable=True),
        sa.Column("download_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["file_id"], ["uploaded_files.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token", name="uq_file_share_links_token"),
    )
    op.create_index("ix_file_share_links_file_id", "file_share_links", ["file_id"])

    op.create_table(
        "group_chat_files",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("group_id", sa.BigInteger(), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=False),
        sa.Column("attachment_index", sa.Integer(), nullable=False),
        sa.Column("file_id", sa.BigInteger(), nullable=True),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("original_name", sa.String(length=512), nullable=False),
        sa.Column("mime_type", sa.String(length=255), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("sender_user_id", sa.BigInteger(), nullable=True),
        sa.Column("sender_contact_id", sa.BigInteger(), nullable=True),
        sa.Column("sender_display_name", sa.String(length=512), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["chat_id"], ["chats.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["file_id"], ["uploaded_files.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sender_contact_id"], ["contacts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["sender_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "message_id",
            "attachment_index",
            name="uq_group_chat_files_message_attachment",
        ),
    )
    op.create_index(
        "ix_group_chat_files_group_id_created_at",
        "group_chat_files",
        ["group_id", "created_at"],
    )
    op.create_index("ix_group_chat_files_chat_id", "group_chat_files", ["chat_id"])


def downgrade() -> None:
    op.drop_index("ix_group_chat_files_chat_id", table_name="group_chat_files")
    op.drop_index("ix_group_chat_files_group_id_created_at", table_name="group_chat_files")
    op.drop_table("group_chat_files")
    op.drop_index("ix_file_share_links_file_id", table_name="file_share_links")
    op.drop_table("file_share_links")
    op.drop_index("ix_file_vault_items_owner_user_id", table_name="file_vault_items")
    op.drop_table("file_vault_items")
    op.alter_column(
        "uploaded_files",
        "uploaded_by",
        existing_type=sa.BigInteger(),
        nullable=False,
    )
