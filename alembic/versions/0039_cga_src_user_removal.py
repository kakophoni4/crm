"""Allow user_removal_rebalance in contact_group_assignments.assignment_source.

Revision ID: 0039_cga_src_user_removal
Revises: 0038_user_deletion_requests
"""

from __future__ import annotations

from alembic import op

revision = "0039_cga_src_user_removal"
down_revision = "0038_user_deletion_requests"
branch_labels = None
depends_on = None


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
                'user_removal_rebalance'
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
                'migration'
            )
        )
        """
    )
