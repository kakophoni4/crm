"""User deletion requests (senior -> admin approval).

Revision ID: 0038_user_deletion_requests
Revises: 0037_reset_open_leads_new
"""

from __future__ import annotations

from alembic import op

revision = "0038_user_deletion_requests"
down_revision = "0037_reset_open_leads_new"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE user_deletion_requests (
            id BIGSERIAL PRIMARY KEY,
            target_user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            requested_by_user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            state TEXT NOT NULL DEFAULT 'pending'
                CHECK (state IN ('pending', 'approved', 'rejected')),
            comment TEXT,
            admin_comment TEXT,
            decided_at TIMESTAMPTZ,
            decided_by_user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_user_deletion_pending_target
        ON user_deletion_requests (target_user_id)
        WHERE state = 'pending'
        """
    )
    op.execute(
        """
        CREATE INDEX idx_user_deletion_requests_state
        ON user_deletion_requests (state, created_at DESC)
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_user_deletion_requests_updated_at
        BEFORE UPDATE ON user_deletion_requests
        FOR EACH ROW
        EXECUTE FUNCTION update_timestamp_trigger()
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_user_deletion_requests_updated_at "
        "ON user_deletion_requests"
    )
    op.execute("DROP TABLE IF EXISTS user_deletion_requests")
