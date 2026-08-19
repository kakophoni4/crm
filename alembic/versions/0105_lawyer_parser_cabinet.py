"""Lawyer role, lavok parser lots, org-check for lawyer.

Revision ID: 0105_lawyer_parser_cabinet
Revises: 0104_task_audit_actions
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0105_lawyer_parser_cabinet"
down_revision: str | None = "0104_task_audit_actions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'lawyer'")

    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_role_org")
    op.execute(
        """
        ALTER TABLE users ADD CONSTRAINT ck_users_role_org CHECK (
            (role = 'user' AND department_id IS NOT NULL)
            OR (role = 'group_senior' AND department_id IS NOT NULL)
            OR (role = 'senior' AND department_id IS NOT NULL AND group_id IS NULL)
            OR (role = 'admin' AND department_id IS NULL AND group_id IS NULL)
            OR (role = 'accountant' AND department_id IS NULL AND group_id IS NULL)
            OR (role = 'chief_accountant' AND department_id IS NULL AND group_id IS NULL)
            OR (role = 'lawyer' AND department_id IS NULL AND group_id IS NULL)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE lavok_parser_lots (
            id BIGSERIAL PRIMARY KEY,
            inn TEXT NOT NULL,
            sheet_date DATE NOT NULL,
            source TEXT,
            name TEXT,
            price TEXT,
            registered_at TEXT,
            tax TEXT,
            address_director TEXT,
            courts TEXT,
            debts TEXT,
            egrul_reliability TEXT,
            bankruptcy TEXT,
            turnover TEXT,
            reporting TEXT,
            leasing TEXT,
            zsk TEXT,
            summary TEXT,
            score TEXT,
            first_seen TEXT,
            seller TEXT,
            link TEXT,
            companium TEXT,
            egrul_status TEXT,
            mark TEXT NOT NULL DEFAULT 'new',
            note TEXT,
            is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_lavok_parser_lots_inn_sheet_date UNIQUE (inn, sheet_date)
        )
        """
    )
    op.execute("CREATE INDEX idx_lavok_parser_lots_sheet_date ON lavok_parser_lots (sheet_date)")
    op.execute("CREATE INDEX idx_lavok_parser_lots_is_deleted ON lavok_parser_lots (is_deleted)")
    op.execute("CREATE INDEX idx_lavok_parser_lots_inn ON lavok_parser_lots (inn)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS lavok_parser_lots")
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_role_org")
    op.execute(
        """
        ALTER TABLE users ADD CONSTRAINT ck_users_role_org CHECK (
            (role = 'user' AND department_id IS NOT NULL)
            OR (role = 'group_senior' AND department_id IS NOT NULL)
            OR (role = 'senior' AND department_id IS NOT NULL AND group_id IS NULL)
            OR (role = 'admin' AND department_id IS NULL AND group_id IS NULL)
            OR (role = 'accountant' AND department_id IS NULL AND group_id IS NULL)
            OR (role = 'chief_accountant' AND department_id IS NULL AND group_id IS NULL)
        )
        """
    )
