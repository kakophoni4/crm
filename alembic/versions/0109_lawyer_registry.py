"""Lawyer registry: shops, directors, salary payments, parser alerts.

Revision ID: 0109_lawyer_registry
Revises: 0108_vault_folder_shares
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0109_lawyer_registry"
down_revision: str | None = "0108_vault_folder_shares"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS lawyer_directors (
            id BIGSERIAL PRIMARY KEY,
            full_name TEXT NOT NULL,
            name_key TEXT NOT NULL UNIQUE,
            salary_plan NUMERIC(14, 2) NULL,
            dirovod TEXT NULL,
            company_status TEXT NULL,
            companies_status TEXT NULL,
            ecsp_status TEXT NULL,
            ecsp_until DATE NULL,
            banks TEXT NULL,
            accounts_status TEXT NULL,
            phone TEXT NULL,
            telegram TEXT NULL,
            passport TEXT NULL,
            inn_personal TEXT NULL,
            snils TEXT NULL,
            birth_date DATE NULL,
            in_touch TEXT NULL,
            note TEXT NULL,
            pinned_at TIMESTAMPTZ NULL,
            created_by BIGINT NULL REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS lawyer_shops (
            id BIGSERIAL PRIMARY KEY,
            inn TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            director_id BIGINT NULL REFERENCES lawyer_directors(id) ON DELETE SET NULL,
            kind TEXT NOT NULL DEFAULT 'priority',
            registered_at DATE NULL,
            planned_payout NUMERIC(14, 2) NULL,
            company_status TEXT NULL,
            sale_priority TEXT NULL,
            unreliable TEXT NULL,
            treatment_status TEXT NULL,
            ecsp_status TEXT NULL,
            ecsp_until DATE NULL,
            zsk TEXT NULL,
            banks TEXT NULL,
            accounts_status TEXT NULL,
            manager TEXT NULL,
            phone TEXT NULL,
            telegram TEXT NULL,
            accountant TEXT NULL,
            comment TEXT NULL,
            source TEXT NOT NULL DEFAULT 'manual',
            last_parser_at TIMESTAMPTZ NULL,
            pinned_at TIMESTAMPTZ NULL,
            created_by BIGINT NULL REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_lawyer_shops_director_id ON lawyer_shops (director_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_lawyer_shops_kind ON lawyer_shops (kind)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_lawyer_shops_pinned_at ON lawyer_shops (pinned_at)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS lawyer_director_payments (
            id BIGSERIAL PRIMARY KEY,
            director_id BIGINT NOT NULL REFERENCES lawyer_directors(id) ON DELETE CASCADE,
            shop_id BIGINT NULL REFERENCES lawyer_shops(id) ON DELETE SET NULL,
            period_ym TEXT NOT NULL,
            amount NUMERIC(14, 2) NOT NULL,
            paid_at DATE NULL,
            note TEXT NULL,
            created_by BIGINT NULL REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_lawyer_director_payments_director_id
        ON lawyer_director_payments (director_id)
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_lawyer_director_payments_dir_shop_period
        ON lawyer_director_payments (director_id, COALESCE(shop_id, 0), period_ym)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS lawyer_parser_alerts (
            id BIGSERIAL PRIMARY KEY,
            shop_id BIGINT NULL REFERENCES lawyer_shops(id) ON DELETE CASCADE,
            inn TEXT NOT NULL,
            title TEXT NOT NULL,
            details TEXT NULL,
            is_read BOOLEAN NOT NULL DEFAULT false,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_lawyer_parser_alerts_is_read ON lawyer_parser_alerts (is_read)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS lawyer_parser_alerts")
    op.execute("DROP TABLE IF EXISTS lawyer_director_payments")
    op.execute("DROP TABLE IF EXISTS lawyer_shops")
    op.execute("DROP TABLE IF EXISTS lawyer_directors")
