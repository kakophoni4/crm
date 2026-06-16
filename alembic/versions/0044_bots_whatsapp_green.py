"""WhatsApp (GREEN API) credentials on bot records.

Revision ID: 0044_bots_whatsapp_green
Revises: 0043_chats_contact_bot_uq
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0044_bots_whatsapp_green"
down_revision = "0043_chats_contact_bot_uq"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "bots",
        sa.Column("channel", sa.Text(), nullable=False, server_default="telegram"),
    )
    op.add_column("bots", sa.Column("green_api_url", sa.Text(), nullable=True))
    op.add_column("bots", sa.Column("green_media_url", sa.Text(), nullable=True))
    op.add_column("bots", sa.Column("green_instance_id", sa.Text(), nullable=True))
    op.add_column("bots", sa.Column("green_api_token_encrypted", sa.LargeBinary(), nullable=True))


def downgrade() -> None:
    op.drop_column("bots", "green_api_token_encrypted")
    op.drop_column("bots", "green_instance_id")
    op.drop_column("bots", "green_media_url")
    op.drop_column("bots", "green_api_url")
    op.drop_column("bots", "channel")
