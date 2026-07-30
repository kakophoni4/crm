"""Add opt_receipts for SBIS KV/IV PDFs.

Revision ID: 0091_opt_receipts
Revises: 0090_opt_unit_volume_limit
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0091_opt_receipts"
down_revision: str | None = "0090_opt_unit_volume_limit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS opt_receipts (
            id BIGSERIAL PRIMARY KEY,
            external_id TEXT NOT NULL,
            supplier_inn TEXT NOT NULL,
            supplier_kpp TEXT NULL,
            supplier_name TEXT NULL,
            period_code TEXT NOT NULL,
            doc_kind TEXT NOT NULL,
            source_filename TEXT NOT NULL,
            parsed_name TEXT NULL,
            pdf_file_id BIGINT NULL REFERENCES uploaded_files(id) ON DELETE SET NULL,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            received_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
            updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
            CONSTRAINT uq_opt_receipts_external_id UNIQUE (external_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_opt_receipts_supplier_period "
        "ON opt_receipts (supplier_inn, period_code)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_opt_receipts_period ON opt_receipts (period_code)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS opt_receipts")
