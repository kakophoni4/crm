"""Per-group escalation settings with defaults.

Revision ID: 0013_group_escalation_settings
Revises: 0012_contact_group_ownership
Create Date: 2026-05-17

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0013_group_escalation_settings"
down_revision: str | None = "0012_contact_group_ownership"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE group_escalation_settings (
            group_id BIGINT PRIMARY KEY REFERENCES groups(id) ON DELETE CASCADE,
            first_response_timeout_minutes INT NOT NULL DEFAULT 15,
            new_contact_reassign_strategy TEXT NOT NULL DEFAULT 'first_responder',
            notify_owner_on_inbound BOOLEAN NOT NULL DEFAULT TRUE,
            notify_group_on_escalation BOOLEAN NOT NULL DEFAULT TRUE,
            updated_by BIGINT REFERENCES users(id) ON DELETE SET NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT chk_ges_reassign_strategy CHECK (
                new_contact_reassign_strategy IN ('first_responder', 'random_available')
            )
        )
        """
    )
    op.execute(
        """
        INSERT INTO group_escalation_settings (group_id)
        SELECT id FROM groups
        ON CONFLICT (group_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS group_escalation_settings")
