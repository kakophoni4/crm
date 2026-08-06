"""Fix false correction flags and generic «ООО Компания» names.

Revision ID: 0095_opt_receipts_fix_correction_names
Revises: 0094_opt_receipts_is_correction
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0095_opt_receipts_fix_correction_names"
down_revision: str | None = "0094_opt_receipts_is_correction"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Clear false positives: only filename markers mean correction.
    op.execute(
        """
        UPDATE opt_receipts
        SET is_correction = false
        WHERE is_correction = true
          AND source_filename NOT ILIKE '%корректир%'
          AND source_filename NOT ILIKE '%уточненн%'
          AND source_filename NOT ILIKE '%уточнённ%'
          AND source_filename NOT ILIKE '%корректирующ%'
        """
    )
    # Prefer lavka name from opt_units when stored name is generic boilerplate.
    op.execute(
        """
        UPDATE opt_receipts r
        SET supplier_name = u.name,
            updated_at = now()
        FROM opt_units u
        WHERE u.inn = r.supplier_inn
          AND (
            r.supplier_name IS NULL
            OR trim(both '\"«»' from regexp_replace(
                lower(r.supplier_name), '^ооо[[:space:]]*', '', 'i'
            )) IN ('компания', 'организация', 'фирма', 'предприятие')
          )
        """
    )
    # Fallback: short name from filename parentheses.
    op.execute(
        """
        UPDATE opt_receipts
        SET supplier_name = substring(source_filename from '\\(([^)]+)\\)'),
            updated_at = now()
        WHERE (
            supplier_name IS NULL
            OR trim(both '\"«»' from regexp_replace(
                lower(supplier_name), '^ооо[[:space:]]*', '', 'i'
            )) IN ('компания', 'организация', 'фирма', 'предприятие')
          )
          AND source_filename ~ '\\([^)]+\\)'
        """
    )


def downgrade() -> None:
    pass
