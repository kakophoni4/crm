"""Add opt_sales_book_extracts for short SBIS sales-book PDFs.

Revision ID: 0096_opt_sales_book_extracts
Revises: 0095_opt_receipts_fix_correction_names
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0096_opt_sales_book_extracts"
down_revision: str | None = "0095_opt_receipts_fix_correction_names"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS opt_sales_book_extracts (
            id BIGSERIAL PRIMARY KEY,
            external_id TEXT NOT NULL,
            seller_inn TEXT NOT NULL,
            buyer_inn TEXT NOT NULL,
            seller_name TEXT NULL,
            buyer_name TEXT NULL,
            source_path TEXT NULL,
            source_filename TEXT NOT NULL,
            pdf_file_id BIGINT NULL REFERENCES uploaded_files(id) ON DELETE SET NULL,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            received_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
            updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
            CONSTRAINT uq_opt_sales_book_extracts_external_id UNIQUE (external_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_opt_sbe_seller_buyer "
        "ON opt_sales_book_extracts (seller_inn, buyer_inn)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_opt_sbe_buyer ON opt_sales_book_extracts (buyer_inn)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS opt_sales_book_extracts")
