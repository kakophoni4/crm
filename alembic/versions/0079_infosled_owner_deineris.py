"""Re-apply Infosled bot default owner to username deineris (idempotent).

Revision ID: 0079_infosled_owner_deineris
Revises: 0078_bot_default_owner
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0079_infosled_owner_deineris"
down_revision: str | None = "0078_bot_default_owner"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
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
        UPDATE bots AS b
        SET default_owner_user_id = NULL
        FROM users AS u
        WHERE lower(u.username) = 'deineris'
          AND b.default_owner_user_id = u.id
          AND (
            b.name ILIKE '%инфослед%'
            OR b.name ILIKE '%infosled%'
            OR b.code ILIKE '%infosled%'
            OR b.code ILIKE '%info_sled%'
            OR b.code ILIKE '%инфослед%'
          )
        """
    )
