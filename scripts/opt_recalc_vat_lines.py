#!/usr/bin/env python3
"""Recalculate VAT split on existing OPT order lines (e.g. 20% -> 22%).

Keeps gross amount unchanged; updates vat_amount and amount_without_vat.
Also patches submission_request JSON for submitted orders (CRM audit/export consistency).

Usage on VPS:
  docker exec crm-staging-api python scripts/opt_recalc_vat_lines.py --dry-run
  docker exec crm-staging-api python scripts/opt_recalc_vat_lines.py --apply
  docker exec crm-staging-api python scripts/opt_recalc_vat_lines.py --apply --rate 22 --lead-id 296
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.modules.db.models.lead_opt_order import LeadOptOrder, LeadOptOrderLine  # noqa: E402
from app.modules.leads.opt.vat import split_vat_included  # noqa: E402
from app.shared.db import get_session_factory  # noqa: E402
from app.shared.settings import get_settings  # noqa: E402


def _implied_rate_percent(line: LeadOptOrderLine) -> Decimal | None:
    wo = Decimal(str(line.amount_without_vat))
    if wo <= 0:
        return None
    vat = Decimal(str(line.vat_amount))
    return (vat / wo * Decimal("100")).quantize(Decimal("0.01"))


def _needs_recalc(line: LeadOptOrderLine, *, target_rate: Decimal, tolerance: Decimal) -> bool:
    amount = Decimal(str(line.amount))
    if amount <= 0:
        return False
    implied = _implied_rate_percent(line)
    if implied is None:
        return True
    return abs(implied - target_rate) > tolerance


def _patch_submission_request(order: LeadOptOrder) -> int:
    payload = order.submission_request
    if not isinstance(payload, dict):
        return 0
    registry = payload.get("Реестр") or payload.get("Registry")
    if not isinstance(registry, list):
        return 0
    by_crm_id = {line.crm_id: line for line in order.lines}
    changed = 0
    for item in registry:
        if not isinstance(item, dict):
            continue
        crm_id = str(item.get("CRMid") or item.get("ID") or "").strip()
        line = by_crm_id.get(crm_id)
        if line is None:
            continue
        new_vat = float(line.vat_amount)
        new_wo = float(line.amount_without_vat)
        if item.get("СуммаНДС") == new_vat and item.get("СуммаБезНДС") == new_wo:
            continue
        item["СуммаНДС"] = new_vat
        item["СуммаБезНДС"] = new_wo
        changed += 1
    if changed:
        order.submission_request = payload
        flag_modified(order, "submission_request")
    return changed


async def _run(
    *,
    apply: bool,
    rate: Decimal,
    tolerance: Decimal,
    lead_id: int | None,
    order_id: int | None,
) -> int:
    session_factory = get_session_factory()
    lines_updated = 0
    orders_patched = 0

    async with session_factory() as session:
        stmt = (
            select(LeadOptOrder)
            .options(selectinload(LeadOptOrder.lines))
            .order_by(LeadOptOrder.id)
        )
        if lead_id is not None:
            stmt = stmt.where(LeadOptOrder.lead_id == lead_id)
        if order_id is not None:
            stmt = stmt.where(LeadOptOrder.id == order_id)

        orders = list((await session.execute(stmt)).scalars().unique().all())
        print(f"Заявок: {len(orders)}, целевая ставка НДС: {rate}%")

        for order in orders:
            order_changed = False
            for line in order.lines:
                if not _needs_recalc(line, target_rate=rate, tolerance=tolerance):
                    continue
                total = Decimal(str(line.amount))
                _, new_vat, new_wo = split_vat_included(total, rate_percent=rate)
                old_vat = Decimal(str(line.vat_amount))
                old_wo = Decimal(str(line.amount_without_vat))
                if new_vat == old_vat and new_wo == old_wo:
                    continue
                print(
                    f"  order={order.id} lead={order.lead_id} no={order.order_no} "
                    f"line={line.line_no} inn={line.supplier_inn} "
                    f"vat {old_vat}->{new_vat} wo {old_wo}->{new_wo}",
                )
                if apply:
                    line.vat_amount = float(new_vat)
                    line.amount_without_vat = float(new_wo)
                lines_updated += 1
                order_changed = True

            if apply and order_changed and order.submission_request:
                patched = _patch_submission_request(order)
                if patched:
                    orders_patched += 1
                    print(f"  patched submission_request rows: {patched} (order {order.id})")

        if apply:
            await session.commit()
        else:
            await session.rollback()

    mode = "APPLY" if apply else "DRY-RUN"
    print(f"{mode}: lines={lines_updated}, submission_requests={orders_patched}")
    return 0


def main() -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Recalculate VAT on OPT order lines")
    parser.add_argument("--apply", action="store_true", help="Persist changes (default: dry-run)")
    parser.add_argument("--dry-run", action="store_true", help="Explicit dry-run")
    parser.add_argument(
        "--rate",
        type=Decimal,
        default=Decimal(str(settings.opt_vat_rate_percent)),
        help="Target VAT percent (default: from OPT_VAT_RATE_PERCENT)",
    )
    parser.add_argument(
        "--tolerance",
        type=Decimal,
        default=Decimal("0.75"),
        help="Skip lines already within this many pp of target rate",
    )
    parser.add_argument("--lead-id", type=int, help="Only one deal")
    parser.add_argument("--order-id", type=int, help="Only one order id")
    args = parser.parse_args()
    apply = args.apply and not args.dry_run
    return asyncio.run(
        _run(
            apply=apply,
            rate=args.rate,
            tolerance=args.tolerance,
            lead_id=args.lead_id,
            order_id=args.order_id,
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())
