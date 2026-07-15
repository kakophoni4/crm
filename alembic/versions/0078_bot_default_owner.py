"""Bot default owner for exclusive assignment (e.g. Infosled → Daenerys).

Revision ID: 0078_bot_default_owner
Revises: 0077_staff_escalation_policies
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0078_bot_default_owner"
down_revision: str | None = "0077_staff_escalation_policies"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE bots
        ADD COLUMN IF NOT EXISTS default_owner_user_id BIGINT NULL
            REFERENCES users(id) ON DELETE SET NULL
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_bots_default_owner_user_id
        ON bots (default_owner_user_id)
        WHERE default_owner_user_id IS NOT NULL
        """
    )
    # Infosled → exclusive owner deineris (Daenerys)
    op.execute(
        """
        UPDATE bots AS b
        SET default_owner_user_id = u.id
        FROM users AS u
        WHERE lower(u.username) = 'deineris'
          AND u.status = 'active'
          AND (
            b.name ILIKE '%инфослед%'
            OR b.name ILIKE '%infosled%'
            OR b.code ILIKE '%infosled%'
            OR b.code ILIKE '%info_sled%'
            OR b.code ILIKE '%инфослед%'
          )
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE bots
        SET default_owner_user_id = NULL
        WHERE default_owner_user_id IN (
            SELECT id FROM users WHERE lower(username) = 'deineris'
        )
        """
    )
    op.execute("DROP INDEX IF EXISTS ix_bots_default_owner_user_id")
    op.execute("ALTER TABLE bots DROP COLUMN IF EXISTS default_owner_user_id")
