"""Allow bot_default_owner in contact_group_assignments.assignment_source.

Revision ID: 0080_cga_bot_default_owner_source
Revises: 0079_infosled_owner_deineris
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0080_cga_bot_default_owner_source"
down_revision: str | None = "0079_infosled_owner_deineris"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE contact_group_assignments DROP CONSTRAINT IF EXISTS chk_cga_assignment_source",
    )
    op.execute(
        """
        ALTER TABLE contact_group_assignments
        ADD CONSTRAINT chk_cga_assignment_source CHECK (
            assignment_source IN (
                'auto_round_robin',
                'auto_first_responder',
                'auto_random_available',
                'manual_transfer',
                'senior_assign',
                'migration',
                'user_removal_rebalance',
                'manual_create',
                'bot_default_owner'
            )
        )
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE contact_group_assignments
        SET assignment_source = 'auto_round_robin'
        WHERE assignment_source = 'bot_default_owner'
        """
    )
    op.execute(
        "ALTER TABLE contact_group_assignments DROP CONSTRAINT IF EXISTS chk_cga_assignment_source",
    )
    op.execute(
        """
        ALTER TABLE contact_group_assignments
        ADD CONSTRAINT chk_cga_assignment_source CHECK (
            assignment_source IN (
                'auto_round_robin',
                'auto_first_responder',
                'auto_random_available',
                'manual_transfer',
                'senior_assign',
                'migration',
                'user_removal_rebalance',
                'manual_create'
            )
        )
        """
    )
