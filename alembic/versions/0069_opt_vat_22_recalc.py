"""Recalculate OPT order line VAT splits from 20% to 22%.

Revision ID: 0069_opt_vat_22_recalc
Revises: 0068_cga_manual_create_source
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from alembic import op
from sqlalchemy import text

revision: str = "0069_opt_vat_22_recalc"
down_revision: str | None = "0068_cga_manual_create_source"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_VAT_DIVISOR = 1.22
_RATE_TOLERANCE_PP = 0.75


def _patch_submission_request(
    payload: dict[str, Any],
    lines_by_crm_id: dict[str, dict[str, Any]],
) -> bool:
    registry = payload.get("Реестр") or payload.get("Registry")
    if not isinstance(registry, list):
        return False
    changed = False
    for item in registry:
        if not isinstance(item, dict):
            continue
        crm_id = str(item.get("CRMid") or item.get("ID") or "").strip()
        line = lines_by_crm_id.get(crm_id)
        if line is None:
            continue
        new_vat = float(line["vat_amount"])
        new_wo = float(line["amount_without_vat"])
        if item.get("СуммаНДС") == new_vat and item.get("СуммаБезНДС") == new_wo:
            continue
        item["СуммаНДС"] = new_vat
        item["СуммаБезНДС"] = new_wo
        changed = True
    return changed


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        text(
            f"""
            UPDATE lead_opt_order_lines
            SET
                amount_without_vat = ROUND(amount / {_VAT_DIVISOR}, 2),
                vat_amount = ROUND(amount - ROUND(amount / {_VAT_DIVISOR}, 2), 2),
                updated_at = now()
            WHERE amount > 0
              AND (
                amount_without_vat <= 0
                OR ABS((vat_amount / amount_without_vat) * 100 - 22) >= {_RATE_TOLERANCE_PP}
              )
            """,
        ),
    )

    orders = conn.execute(
        text(
            """
            SELECT id, submission_request
            FROM lead_opt_orders
            WHERE submission_request IS NOT NULL
            """,
        ),
    ).mappings().all()

    for order in orders:
        payload = order["submission_request"]
        if not isinstance(payload, dict):
            continue
        line_rows = conn.execute(
            text(
                """
                SELECT crm_id, vat_amount, amount_without_vat
                FROM lead_opt_order_lines
                WHERE order_id = :order_id
                """,
            ),
            {"order_id": order["id"]},
        ).mappings().all()
        lines_by_crm_id = {str(row["crm_id"]): row for row in line_rows}
        if not _patch_submission_request(payload, lines_by_crm_id):
            continue
        conn.execute(
            text(
                """
                UPDATE lead_opt_orders
                SET submission_request = CAST(:payload AS jsonb),
                    updated_at = now()
                WHERE id = :order_id
                """,
            ),
            {"payload": json.dumps(payload, ensure_ascii=False), "order_id": order["id"]},
        )


def downgrade() -> None:
    pass
