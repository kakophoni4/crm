"""Simplify lead pipeline to new + in_progress; keep won/lost for close only.

Revision ID: 0036_simplify_pipeline
Revises: 0035_pipeline_outcome_labels
"""

from __future__ import annotations

from alembic import op

revision = "0036_simplify_pipeline"
down_revision = "0035_pipeline_outcome_labels"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE statuses
        SET label = 'Новый', sort_order = 0
        WHERE kind = 'lead_pipeline' AND code = 'new'
        """
    )
    op.execute(
        """
        UPDATE statuses
        SET label = 'В работе', sort_order = 10
        WHERE kind = 'lead_pipeline' AND code = 'in_progress'
        """
    )
    op.execute(
        """
        UPDATE statuses
        SET label = 'Успешная продажа', sort_order = 900
        WHERE kind = 'lead_pipeline' AND code = 'won'
        """
    )
    op.execute(
        """
        UPDATE statuses
        SET label = 'Неуспешная продажа', sort_order = 910
        WHERE kind = 'lead_pipeline' AND code = 'lost'
        """
    )

    op.execute(
        """
        UPDATE leads l
        SET status_id = ip.id
        FROM statuses ip
        WHERE l.closed_at IS NULL
          AND ip.kind = 'lead_pipeline'
          AND ip.code = 'in_progress'
          AND l.status_id IN (
              SELECT s.id
              FROM statuses s
              WHERE s.kind = 'lead_pipeline'
                AND s.code NOT IN ('new', 'in_progress')
          )
        """
    )

    op.execute(
        """
        UPDATE leads l
        SET status_id = w.id
        FROM statuses w
        WHERE l.closed_at IS NOT NULL
          AND w.kind = 'lead_pipeline'
          AND w.code = 'won'
          AND l.status_id IN (
              SELECT s.id
              FROM statuses s
              WHERE s.kind = 'lead_pipeline'
                AND s.code NOT IN ('new', 'in_progress', 'won', 'lost')
          )
        """
    )

    op.execute(
        """
        DELETE FROM statuses s
        WHERE s.kind = 'lead_pipeline'
          AND s.code NOT IN ('new', 'in_progress', 'won', 'lost')
          AND NOT EXISTS (
              SELECT 1 FROM leads l WHERE l.status_id = s.id
          )
        """
    )


def downgrade() -> None:
    for code, label, color, sort_order in (
        ("qualified", "Квалифицирован", "#3B82F6", 20),
    ):
        op.execute(
            f"""
            INSERT INTO statuses (code, kind, label, color, sort_order, is_active)
            SELECT '{code}', 'lead_pipeline', '{label}', '{color}', {sort_order}, true
            WHERE NOT EXISTS (
                SELECT 1 FROM statuses
                WHERE code = '{code}' AND kind = 'lead_pipeline'
            )
            """
        )
