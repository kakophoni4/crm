#!/usr/bin/env python3
"""Remove mistaken trailing lines from OPT order 14 (АТК) after truncated-repair.

Those two lines (16.06/132600 and 23.06/568365) belong to the Tavrida remainder,
not to АТК. Recalc commission; optionally re-queue 1C submit.

Usage:
  docker exec crm-staging-api python /app/scripts/opt_fix_order14_extra_lines.py --dry-run
  docker exec crm-staging-api python /app/scripts/opt_fix_order14_extra_lines.py --apply
  docker exec crm-staging-api python /app/scripts/opt_fix_order14_extra_lines.py --apply --submit
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from decimal import Decimal
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.modules.db.models.lead_opt_order import LeadOptOrder, LeadOptOrderLine
from app.modules.leads.opt.mole_client import get_order
from app.modules.leads.opt.queue import enqueue_opt_submit
from app.modules.leads.opt.repository import OptOrderRepository
from app.shared.db import get_session_factory

ORDER_ID = 249  # lead 363, order_no 14

# Exact extras from accountant/registry screenshot
EXTRA = {
    (Decimal("132600.00"), "2026-06-16"),
    (Decimal("568365.00"), "2026-06-23"),
}


def _amt(v: object) -> Decimal:
    return Decimal(str(v or 0)).quantize(Decimal("0.01"))


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--submit", action="store_true", help="queue 1C submit after apply")
    parser.add_argument("--order-id", type=int, default=ORDER_ID)
    args = parser.parse_args()
    if not args.dry_run and not args.apply:
        args.dry_run = True

    sf = get_session_factory()
    async with sf() as session:
        repo = OptOrderRepository(session)
        order = (
            await session.execute(
                select(LeadOptOrder)
                .where(LeadOptOrder.id == args.order_id)
                .options(selectinload(LeadOptOrder.lines))
            )
        ).scalar_one_or_none()
        if order is None:
            print(f"order {args.order_id} missing")
            return 1

        print(
            f"order={order.id} no={order.order_no} buyer={order.buyer_inn} "
            f"vol={order.total_volume} lines={len(order.lines)} file={order.source_filename}"
        )
        remove: list[LeadOptOrderLine] = []
        keep: list[LeadOptOrderLine] = []
        for ln in sorted(order.lines, key=lambda x: x.line_no):
            key = (_amt(ln.amount), ln.document_date.isoformat() if ln.document_date else "")
            mark = "REMOVE" if key in EXTRA else "KEEP"
            print(
                f"  {mark} L{ln.line_no} {ln.supplier_inn} {ln.document_date} "
                f"{_amt(ln.amount)} doc={ln.document_number}"
            )
            if key in EXTRA:
                remove.append(ln)
            else:
                keep.append(ln)

        if len(remove) != 2:
            print(f"ERROR: expected 2 extras, found {len(remove)} — abort")
            return 2

        keep_vol = sum((_amt(ln.amount) for ln in keep), Decimal("0"))
        print(f"after: lines={len(keep)} vol={keep_vol}")

        try:
            mole = await get_order(order.crm_id)
            print(f"Mole sum now={mole.get('СуммаИтого')} (crm will be {keep_vol})")
        except Exception as exc:  # noqa: BLE001
            print(f"Mole GET: {exc}")

        if args.dry_run or not args.apply:
            print("dry-run only")
            return 0

        for ln in remove:
            await session.delete(ln)
        await session.flush()
        await session.refresh(order, attribute_names=["lines"])
        for i, ln in enumerate(sorted(order.lines, key=lambda x: x.line_no), start=1):
            ln.line_no = i
        await session.flush()
        await session.refresh(order, attribute_names=["lines"])
        await repo.apply_pricing_snapshot(order)

        if args.submit:
            order.status = "queued"
            order.submission_error = None
            await session.commit()
            await enqueue_opt_submit(order.id)
            print(
                f"APPLIED order={order.id} vol={order.total_volume} "
                f"lines={len(order.lines)} QUEUED→1C"
            )
        else:
            order.status = "submitted"
            await session.commit()
            print(
                f"APPLIED order={order.id} vol={order.total_volume} "
                f"lines={len(order.lines)} (CRM only; pass --submit to push 1C)"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
