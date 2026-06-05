"""Rename won/lost pipeline labels to sale outcomes.

Revision ID: 0035_pipeline_outcome_labels
Revises: 0034_lead_comment_backfill
"""

from __future__ import annotations

from alembic import op

revision = "0035_pipeline_outcome_labels"
down_revision = "0034_lead_comment_backfill"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE statuses
        SET label = 'Успешная продажа'
        WHERE kind = 'lead_pipeline' AND code = 'won'
        """
    )
    op.execute(
        """
        UPDATE statuses
        SET label = 'Неуспешная продажа'
        WHERE kind = 'lead_pipeline' AND code = 'lost'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE statuses
        SET label = 'Выигран'
        WHERE kind = 'lead_pipeline' AND code = 'won'
        """
    )
    op.execute(
        """
        UPDATE statuses
        SET label = 'Проигран'
        WHERE kind = 'lead_pipeline' AND code = 'lost'
        """
    )
