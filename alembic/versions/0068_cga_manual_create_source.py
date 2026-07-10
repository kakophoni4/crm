"""Allow manual_create in contact_group_assignments.assignment_source.

Revision ID: 0068_cga_manual_create_source
Revises: 0067_chat_list_perf_indexes
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0068_cga_manual_create_source"
down_revision: str | None = "0067_chat_list_perf_indexes"
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
                'manual_create'
            )
        )
        """
    )


def downgrade() -> None:
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
                'user_removal_rebalance'
            )
        )
        """
    )
