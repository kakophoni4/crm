"""Operator file uploads for chat attachments.

Revision ID: 0040_uploaded_files
Revises: 0039_cga_src_user_removal
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0040_uploaded_files"
down_revision = "0039_cga_src_user_removal"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "uploaded_files",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("original_name", sa.String(length=512), nullable=False),
        sa.Column("mime_type", sa.String(length=255), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("uploaded_by", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_uploaded_files_uploaded_by", "uploaded_files", ["uploaded_by"])


def downgrade() -> None:
    op.drop_index("ix_uploaded_files_uploaded_by", table_name="uploaded_files")
    op.drop_table("uploaded_files")
