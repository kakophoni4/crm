"""OPT wholesale orders (заявки) and supplier units (лавки).

Revision ID: 0054_lead_opt_orders
Revises: 0053_quick_reply_template_hidden
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0054_lead_opt_orders"
down_revision: str | None = "0053_quick_reply_template_hidden"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE opt_units (
            id BIGSERIAL PRIMARY KEY,
            inn TEXT NOT NULL,
            kpp TEXT,
            name TEXT NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_opt_units_inn UNIQUE (inn)
        );

        CREATE TABLE lead_opt_orders (
            id BIGSERIAL PRIMARY KEY,
            lead_id BIGINT NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
            crm_id TEXT NOT NULL,
            buyer_inn TEXT NOT NULL,
            buyer_kpp TEXT,
            buyer_name TEXT,
            status TEXT NOT NULL DEFAULT 'draft',
            source_filename TEXT,
            submission_request JSONB,
            submission_response JSONB,
            submission_error TEXT,
            submitted_at TIMESTAMPTZ,
            submitted_by BIGINT REFERENCES users(id) ON DELETE SET NULL,
            created_by BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_lead_opt_orders_crm_id UNIQUE (crm_id)
        );
        CREATE INDEX idx_lead_opt_orders_lead_id ON lead_opt_orders(lead_id);

        CREATE TABLE lead_opt_order_lines (
            id BIGSERIAL PRIMARY KEY,
            order_id BIGINT NOT NULL REFERENCES lead_opt_orders(id) ON DELETE CASCADE,
            crm_id TEXT NOT NULL,
            line_no INT NOT NULL,
            supplier_inn TEXT NOT NULL,
            supplier_kpp TEXT,
            supplier_name TEXT,
            document_date DATE NOT NULL,
            amount NUMERIC(15, 2) NOT NULL,
            vat_amount NUMERIC(15, 2) NOT NULL,
            amount_without_vat NUMERIC(15, 2) NOT NULL,
            document_number TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_lead_opt_order_lines_crm_id UNIQUE (crm_id)
        );
        CREATE INDEX idx_lead_opt_order_lines_order_id ON lead_opt_order_lines(order_id);

        INSERT INTO opt_units (inn, kpp, name) VALUES
            ('7743622734', '774301001', 'СПЕЦАВТОТРАНССЕРВИС ООО'),
            ('7713151911', '771401001', 'СК ДОМРЕМСТРОЙ ПЛЮС ООО'),
            ('7720313708', '772001001', 'АСВ-ТЕХНОЛОГИИ ООО'),
            ('7703822568', NULL, 'Лавка 7703822568')
        ON CONFLICT (inn) DO NOTHING;
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS lead_opt_order_lines")
    op.execute("DROP TABLE IF EXISTS lead_opt_orders")
    op.execute("DROP TABLE IF EXISTS opt_units")
