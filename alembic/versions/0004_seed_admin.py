"""Seed initial admin user.

Revision ID: 0004_seed_admin
Revises: 0003_core_identity
Create Date: 2026-05-16

"""

from __future__ import annotations

import os
from collections.abc import Sequence

import bcrypt

from alembic import op

revision: str = "0004_seed_admin"
down_revision: str | None = "0003_core_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DEFAULT_EMAIL = "admin@crm.local"
_DEFAULT_PASSWORD = "ChangeMe!234567"


def _admin_email() -> str:
    return os.getenv("SEED_ADMIN_EMAIL", _DEFAULT_EMAIL)


def _admin_password_hash() -> str:
    # passlib 1.7 is incompatible with bcrypt 4.1+; use bcrypt directly ($2b$).
    password = os.getenv("SEED_ADMIN_PASSWORD", _DEFAULT_PASSWORD)
    digest = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12))
    return digest.decode("utf-8")


def upgrade() -> None:
    email = _admin_email()
    password_hash = _admin_password_hash()
    email_sql = email.replace("'", "''")
    hash_sql = password_hash.replace("'", "''")
    op.execute(
        f"""
        INSERT INTO users (
            email,
            password_hash,
            full_name,
            role,
            department_id,
            group_id
        )
        VALUES (
            '{email_sql}',
            '{hash_sql}',
            'System Administrator',
            'admin',
            NULL,
            NULL
        )
        ON CONFLICT (email) DO NOTHING
        """
    )


def downgrade() -> None:
    email = _admin_email().replace("'", "''")
    op.execute(
        f"""
        DELETE FROM users
        WHERE email = '{email}'
          AND role = 'admin'
          AND department_id IS NULL
          AND group_id IS NULL
        """
    )
