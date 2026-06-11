"""Multi-group operator membership.

Revision ID: 0042_user_group_memberships
Revises: 0041_bot_department_groups
"""

from __future__ import annotations

from alembic import op

revision = "0042_user_group_memberships"
down_revision = "0041_bot_department_groups"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE user_group_memberships (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            group_id BIGINT NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (user_id, group_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_user_group_memberships_user_id ON user_group_memberships (user_id)"
    )
    op.execute(
        "CREATE INDEX ix_user_group_memberships_group_id ON user_group_memberships (group_id)"
    )
    op.execute(
        """
        INSERT INTO user_group_memberships (user_id, group_id)
        SELECT id, group_id FROM users
        WHERE group_id IS NOT NULL
        ON CONFLICT (user_id, group_id) DO NOTHING
        """
    )
    op.execute("ALTER TABLE users DROP CONSTRAINT ck_users_role_org")
    op.execute(
        """
        ALTER TABLE users ADD CONSTRAINT ck_users_role_org CHECK (
            (role = 'user' AND department_id IS NOT NULL)
            OR (role = 'senior' AND department_id IS NOT NULL AND group_id IS NULL)
            OR (role = 'admin' AND department_id IS NULL AND group_id IS NULL)
        )
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE users u
        SET group_id = sub.group_id
        FROM (
            SELECT DISTINCT ON (user_id) user_id, group_id
            FROM user_group_memberships
            ORDER BY user_id, group_id
        ) sub
        WHERE u.id = sub.user_id
          AND u.role = 'user'
          AND u.group_id IS NULL
        """
    )
    op.execute("DROP TABLE IF EXISTS user_group_memberships")
    op.execute("ALTER TABLE users DROP CONSTRAINT ck_users_role_org")
    op.execute(
        """
        ALTER TABLE users ADD CONSTRAINT ck_users_role_org CHECK (
            (role = 'user' AND group_id IS NOT NULL)
            OR (role = 'senior' AND department_id IS NOT NULL AND group_id IS NULL)
            OR (role = 'admin' AND department_id IS NULL AND group_id IS NULL)
        )
        """
    )
