"""Accounting cabinet: accountant role, lavka assignments, requirements.

Revision ID: 0065_accounting_cabinet
Revises: 0064_opt_unit_commission_rate
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0065_accounting_cabinet"
down_revision: str | None = "0064_opt_unit_commission_rate"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'accountant'")

    op.execute(
        """
        CREATE TABLE opt_accountant_unit_assignments (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            unit_id BIGINT NOT NULL REFERENCES opt_units(id) ON DELETE CASCADE,
            assigned_by BIGINT REFERENCES users(id) ON DELETE SET NULL,
            assigned_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_opt_accountant_unit UNIQUE (user_id, unit_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_opt_accountant_unit_user_id ON opt_accountant_unit_assignments (user_id)"
    )
    op.execute(
        "CREATE INDEX idx_opt_accountant_unit_unit_id ON opt_accountant_unit_assignments (unit_id)"
    )

    op.execute(
        """
        CREATE TABLE opt_requirements (
            id BIGSERIAL PRIMARY KEY,
            external_id TEXT NOT NULL UNIQUE,
            supplier_inn TEXT NOT NULL,
            supplier_kpp TEXT,
            supplier_name TEXT,
            title TEXT NOT NULL,
            description TEXT,
            status TEXT NOT NULL DEFAULT 'new',
            pdf_file_id BIGINT REFERENCES uploaded_files(id) ON DELETE SET NULL,
            metadata JSONB NOT NULL DEFAULT '{}',
            received_at TIMESTAMPTZ NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX idx_opt_requirements_supplier_inn ON opt_requirements (supplier_inn)")
    op.execute("CREATE INDEX idx_opt_requirements_received_at ON opt_requirements (received_at)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS opt_requirements")
    op.execute("DROP TABLE IF EXISTS opt_accountant_unit_assignments")
