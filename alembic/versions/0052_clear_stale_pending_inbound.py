"""Clear stale pending_inbound when the last message is already outbound.

Revision ID: 0052_clear_stale_pending_inbound
Revises: 0051_chat_workflow_statuses
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0052_clear_stale_pending_inbound"
down_revision: str | None = "0051_chat_workflow_statuses"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        WITH latest AS (
            SELECT DISTINCT ON (m.chat_id)
                m.chat_id,
                m.direction,
                c.contact_id,
                c.assigned_group_id,
                c.assigned_department_id
            FROM messages m
            JOIN chats c ON c.id = m.chat_id
            ORDER BY m.chat_id, m.created_at DESC, m.id DESC
        ),
        owner_group AS (
            SELECT
                l.chat_id,
                l.contact_id,
                COALESCE(
                    l.assigned_group_id,
                    (
                        SELECT g.id
                        FROM groups g
                        WHERE g.department_id = l.assigned_department_id
                          AND g.name = '__department_inbox__'
                        LIMIT 1
                    )
                ) AS group_id
            FROM latest l
        )
        UPDATE contact_group_assignments cga
        SET pending_inbound_at = NULL
        FROM latest l
        JOIN owner_group og ON og.chat_id = l.chat_id
        WHERE l.direction = 'outbound'
          AND cga.contact_id = og.contact_id
          AND cga.group_id = og.group_id
          AND cga.pending_inbound_at IS NOT NULL
        """
    )


def downgrade() -> None:
    pass
