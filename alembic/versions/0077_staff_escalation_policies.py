"""Scoped staff escalation policies (org / department / group).

Revision ID: 0077_staff_escalation_policies
Revises: 0076_staff_notifications
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0077_staff_escalation_policies"
down_revision: str | None = "0076_staff_notifications"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE staff_escalation_policies (
            id BIGSERIAL PRIMARY KEY,
            scope TEXT NOT NULL
                CHECK (scope IN ('org', 'department', 'group')),
            department_id BIGINT NULL REFERENCES departments(id) ON DELETE CASCADE,
            group_id BIGINT NULL REFERENCES groups(id) ON DELETE CASCADE,
            timeout_minutes INTEGER NOT NULL DEFAULT 15
                CHECK (timeout_minutes >= 1 AND timeout_minutes <= 1440),
            mute_phrases JSONB NOT NULL DEFAULT '[]'::jsonb,
            updated_by BIGINT NULL REFERENCES users(id) ON DELETE SET NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_staff_esc_scope_ids CHECK (
                (scope = 'org' AND department_id IS NULL AND group_id IS NULL)
                OR (scope = 'department' AND department_id IS NOT NULL AND group_id IS NULL)
                OR (scope = 'group' AND group_id IS NOT NULL AND department_id IS NULL)
            )
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_staff_esc_org
            ON staff_escalation_policies ((true))
            WHERE scope = 'org'
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_staff_esc_department
            ON staff_escalation_policies (department_id)
            WHERE scope = 'department'
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_staff_esc_group
            ON staff_escalation_policies (group_id)
            WHERE scope = 'group'
        """
    )
    # Seed group policies from existing personal settings of group seniors.
    op.execute(
        """
        INSERT INTO staff_escalation_policies (
            scope, group_id, timeout_minutes, mute_phrases, updated_by, updated_at
        )
        SELECT DISTINCT ON (ugm.group_id)
            'group',
            ugm.group_id,
            COALESCE(uns.group_senior_timeout_minutes, 15),
            COALESCE(uns.mute_phrases, '[]'::jsonb),
            u.id,
            now()
        FROM users u
        JOIN user_group_memberships ugm ON ugm.user_id = u.id
        LEFT JOIN user_notification_settings uns ON uns.user_id = u.id
        WHERE u.role = 'group_senior'
          AND u.status = 'active'
        ORDER BY ugm.group_id, uns.updated_at DESC NULLS LAST, u.id
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS staff_escalation_policies")
