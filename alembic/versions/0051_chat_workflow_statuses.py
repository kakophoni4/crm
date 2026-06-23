"""Add missing chat workflow statuses (new, waiting, done) and backfill waiting.

Revision ID: 0051_chat_workflow_statuses
Revises: 0050_allow_multiple_open_leads
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0051_chat_workflow_statuses"
down_revision: str | None = "0050_allow_multiple_open_leads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CHAT_WORKFLOW_SEED: list[tuple[str, str, str, int]] = [
    ("new", "Новый", "#3498DB", 0),
    ("waiting", "Ожидает ответа", "#9B59B6", 1),
    ("done", "Завершён", "#27AE60", 3),
]


def upgrade() -> None:
    for code, label, color, sort_order in _CHAT_WORKFLOW_SEED:
        op.execute(
            f"""
            INSERT INTO statuses (code, kind, label, color, sort_order, is_active)
            SELECT '{code}', 'chat_label', '{label}', '{color}', {sort_order}, true
            WHERE NOT EXISTS (
                SELECT 1 FROM statuses WHERE code = '{code}' AND kind = 'chat_label'
            )
            """
        )

    op.execute(
        """
        INSERT INTO statuses (code, kind, label, color, sort_order, is_active)
        SELECT 'answered', 'chat_label', 'Отвечен', '#F39C12', 2, true
        WHERE NOT EXISTS (
            SELECT 1 FROM statuses WHERE code = 'answered' AND kind = 'chat_label'
        )
        """
    )

    op.execute(
        """
        WITH latest AS (
            SELECT DISTINCT ON (m.chat_id)
                m.chat_id,
                m.direction
            FROM messages m
            ORDER BY m.chat_id, m.created_at DESC, m.id DESC
        ),
        waiting_status AS (
            SELECT id FROM statuses
            WHERE code = 'waiting' AND kind = 'chat_label'
            LIMIT 1
        ),
        answered_status AS (
            SELECT id FROM statuses
            WHERE code = 'answered' AND kind = 'chat_label'
            LIMIT 1
        )
        UPDATE chats c
        SET status_id = waiting_status.id
        FROM latest l, waiting_status, answered_status
        WHERE c.id = l.chat_id
          AND l.direction = 'inbound'
          AND c.status_id = answered_status.id
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE chats c
        SET status_id = answered_status.id
        FROM statuses waiting_status, statuses answered_status
        WHERE waiting_status.code = 'waiting'
          AND waiting_status.kind = 'chat_label'
          AND answered_status.code = 'answered'
          AND answered_status.kind = 'chat_label'
          AND c.status_id = waiting_status.id
        """
    )

    for code, _, _, _ in _CHAT_WORKFLOW_SEED:
        op.execute(
            f"""
            DELETE FROM statuses
            WHERE code = '{code}' AND kind = 'chat_label'
            """
        )
