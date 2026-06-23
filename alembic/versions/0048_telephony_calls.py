"""Telephony call history.

Revision ID: 0048_telephony_calls
Revises: 0047_telephony_account_groups
"""

from __future__ import annotations

from alembic import op

revision = "0048_telephony_calls"
down_revision = "0047_telephony_account_groups"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE telephony_calls (
            id BIGSERIAL PRIMARY KEY,
            account_id BIGINT NOT NULL REFERENCES telephony_accounts(id) ON DELETE CASCADE,
            user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            department_id BIGINT NOT NULL REFERENCES departments(id) ON DELETE RESTRICT,
            group_id BIGINT NULL REFERENCES groups(id) ON DELETE SET NULL,
            direction TEXT NOT NULL DEFAULT 'outbound',
            phone_number TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'calling',
            duration_seconds INTEGER NULL,
            started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            answered_at TIMESTAMPTZ NULL,
            ended_at TIMESTAMPTZ NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX idx_telephony_calls_account_id ON telephony_calls (account_id)")
    op.execute("CREATE INDEX idx_telephony_calls_user_id ON telephony_calls (user_id)")
    op.execute("CREATE INDEX idx_telephony_calls_department_id ON telephony_calls (department_id)")
    op.execute("CREATE INDEX idx_telephony_calls_group_id ON telephony_calls (group_id)")
    op.execute("CREATE INDEX idx_telephony_calls_started_at ON telephony_calls (started_at DESC)")
    op.execute(
        """
        ALTER TABLE telephony_calls
        ADD CONSTRAINT ck_telephony_calls_direction
        CHECK (direction IN ('outbound', 'inbound'))
        """
    )
    op.execute(
        """
        ALTER TABLE telephony_calls
        ADD CONSTRAINT ck_telephony_calls_status
        CHECK (status IN ('calling', 'answered', 'completed', 'failed'))
        """
    )
    op.execute(
        """
        ALTER TABLE telephony_calls
        ADD CONSTRAINT ck_telephony_calls_duration_nonnegative
        CHECK (duration_seconds IS NULL OR duration_seconds >= 0)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS telephony_calls")
