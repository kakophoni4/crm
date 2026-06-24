"""Per-user hidden quick reply templates.

Revision ID: 0053_quick_reply_template_hidden
Revises: 0052_clear_stale_pending_inbound
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0053_quick_reply_template_hidden"
down_revision: str | None = "0052_clear_stale_pending_inbound"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE quick_reply_template_hidden (
            id BIGSERIAL PRIMARY KEY,
            template_id BIGINT NOT NULL
                REFERENCES quick_reply_templates(id) ON DELETE CASCADE,
            user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            hidden_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_quick_reply_template_hidden_user
                UNIQUE (template_id, user_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_quick_reply_template_hidden_template "
        "ON quick_reply_template_hidden (template_id)"
    )
    op.execute(
        "CREATE INDEX idx_quick_reply_template_hidden_user "
        "ON quick_reply_template_hidden (user_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS quick_reply_template_hidden")
