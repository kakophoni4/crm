"""OPT lavka availability by period + order period snapshot.

Revision ID: 0082_opt_unit_periods
Revises: 0081_opt_order_vat_rate
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0082_opt_unit_periods"
down_revision: str | None = "0081_opt_order_vat_rate"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PARK_2Q26 = (
    "7708721010",
    "9729097741",
    "9731112362",
    "9718148521",
    "7743359603",
    "7724774530",
    "9731112429",
    "7734474261",
    "9731112323",
    "9729355449",
    "5011036907",
    "9718078916",
    "9719029573",
)

_SPECIAL = (
    ("7733419099", "3/25", "Привет"),
    ("7733428671", "3/25", "Иволга"),
    ("7733418909", "4/25", "Спектр"),
    ("7733430705", "4/25", "Орион"),
)


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS opt_unit_period_availability (
            id BIGSERIAL PRIMARY KEY,
            inn TEXT NOT NULL,
            period_code TEXT NOT NULL,
            unit_id BIGINT REFERENCES opt_units(id) ON DELETE SET NULL,
            note TEXT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_opt_unit_period_inn_code UNIQUE (inn, period_code)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_opt_unit_period_code "
        "ON opt_unit_period_availability (period_code)",
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_opt_unit_period_inn "
        "ON opt_unit_period_availability (inn)",
    )
    op.execute(
        """
        ALTER TABLE lead_opt_orders
        ADD COLUMN IF NOT EXISTS period_code TEXT NULL
        """
    )

    for inn in _PARK_2Q26:
        op.execute(
            f"""
            INSERT INTO opt_unit_period_availability (inn, period_code, unit_id, note)
            SELECT '{inn}', '2/26', u.id, 'Парк 2КВ2026'
            FROM opt_units u
            WHERE u.inn = '{inn}'
            ON CONFLICT (inn, period_code) DO NOTHING
            """
        )

    for inn, period, name in _SPECIAL:
        safe_name = name.replace("'", "''")
        op.execute(
            f"""
            INSERT INTO opt_units (inn, name, category_code, commission_rate_percent, is_active)
            SELECT '{inn}', '{safe_name}', 'TECH', 1.10, TRUE
            WHERE NOT EXISTS (SELECT 1 FROM opt_units WHERE inn = '{inn}')
            """
        )
        op.execute(
            f"""
            UPDATE opt_units
            SET is_active = TRUE
            WHERE inn = '{inn}'
            """
        )
        op.execute(
            f"""
            INSERT INTO opt_unit_period_availability (inn, period_code, unit_id, note)
            SELECT '{inn}', '{period}', u.id, 'Перестановка {safe_name}'
            FROM opt_units u
            WHERE u.inn = '{inn}'
            ON CONFLICT (inn, period_code) DO NOTHING
            """
        )


def downgrade() -> None:
    op.execute("ALTER TABLE lead_opt_orders DROP COLUMN IF EXISTS period_code")
    op.execute("DROP TABLE IF EXISTS opt_unit_period_availability")
