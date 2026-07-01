"""OPT buyer directory (clients) with INN/KPP/name for 1C.

Revision ID: 0058_opt_buyers
Revises: 0057_opt_payments
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0058_opt_buyers"
down_revision: str | None = "0057_opt_payments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE opt_buyers (
            id BIGSERIAL PRIMARY KEY,
            inn TEXT NOT NULL UNIQUE,
            kpp TEXT,
            name TEXT NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        INSERT INTO opt_buyers (inn, kpp, name) VALUES
            ('5507266215', '550701001', 'НАВЕЛ КО ООО')
        ON CONFLICT (inn) DO UPDATE SET
            kpp = EXCLUDED.kpp,
            name = EXCLUDED.name,
            is_active = TRUE;
        """,
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS opt_buyers;")
