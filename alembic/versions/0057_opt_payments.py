"""OPT unit categories, order pricing snapshot, payments.

Revision ID: 0057_opt_payments
Revises: 0056_opt_order_no
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from alembic import op

revision: str = "0057_opt_payments"
down_revision: str | None = "0056_opt_order_no"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE opt_units
        ADD COLUMN category_code TEXT NOT NULL DEFAULT 'TECH';

        UPDATE opt_units SET category_code = 'TECH' WHERE category_code IS NULL;

        ALTER TABLE lead_opt_orders
        ADD COLUMN payment_status TEXT NOT NULL DEFAULT 'unpaid',
        ADD COLUMN total_volume NUMERIC(15, 2) NOT NULL DEFAULT 0,
        ADD COLUMN commission_due NUMERIC(15, 2) NOT NULL DEFAULT 0,
        ADD COLUMN amount_paid NUMERIC(15, 2) NOT NULL DEFAULT 0,
        ADD COLUMN volume_by_category JSONB NOT NULL DEFAULT '{}'::jsonb;

        CREATE TABLE lead_opt_order_payments (
            id BIGSERIAL PRIMARY KEY,
            order_id BIGINT NOT NULL REFERENCES lead_opt_orders(id) ON DELETE CASCADE,
            amount NUMERIC(15, 2) NOT NULL,
            paid_at TIMESTAMPTZ NOT NULL,
            payment_type TEXT NOT NULL,
            recipient TEXT NOT NULL,
            created_by BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX idx_lead_opt_order_payments_order_id ON lead_opt_order_payments(order_id);
        """
    )

    seed_path = Path(__file__).resolve().parents[2] / "scripts" / "fixtures" / "opt_units.example.json"
    if seed_path.is_file():
        units = json.loads(seed_path.read_text(encoding="utf-8"))
        for unit in units:
            inn = str(unit["inn"]).strip()
            name = str(unit["name"]).strip().replace("'", "''")
            op.execute(
                f"""
                INSERT INTO opt_units (inn, name, category_code, is_active)
                VALUES ('{inn}', '{name}', 'TECH', TRUE)
                ON CONFLICT (inn) DO UPDATE SET
                    name = EXCLUDED.name,
                    category_code = COALESCE(opt_units.category_code, 'TECH')
                """
            )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS lead_opt_order_payments")
    op.execute(
        """
        ALTER TABLE lead_opt_orders
        DROP COLUMN IF EXISTS volume_by_category,
        DROP COLUMN IF EXISTS amount_paid,
        DROP COLUMN IF EXISTS commission_due,
        DROP COLUMN IF EXISTS total_volume,
        DROP COLUMN IF EXISTS payment_status
        """
    )
    op.execute("ALTER TABLE opt_units DROP COLUMN IF EXISTS category_code")
