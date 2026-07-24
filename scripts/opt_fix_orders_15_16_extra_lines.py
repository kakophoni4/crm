#!/usr/bin/env python3
"""Remove last 2 mistaken trailing lines from OPT orders 15 and 16 (lead 363).

Same truncated-repair junk as order 14: often 16.06/132600 + 23.06/568365.

Usage:
  docker exec crm-staging-api python /app/scripts/opt_fix_orders_15_16_extra_lines.py --dry-run
  docker exec crm-staging-api python /app/scripts/opt_fix_orders_15_16_extra_lines.py --apply
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
from app.modules.leads.opt.queue import enqueue_opt_submit
from app.modules.leads.opt.repository import OptOrderRepository
from app.shared.db import get_session_factory

# Prefer by id (stable); order_no can renumber.
TARGETS = [
    {"order_id": 250, "order_no": 15},
    {"order_id": 253, "order_no": 16},
]

# Known extras (same amounts/dates as order 14 junk / Tavrida испр tail)
KNOWN_EXTRA = {
    (Decimal("132600.00"), "2026-06-16"),
    (Decimal("568365.00"), "2026-06-23"),
}


def _amt(v: object) -> Decimal:
    return Decimal(str(v or 0)).quantize(Decimal("0.01"))


async def _fix_one(
    session,
    repo: OptOrderRepository,
    *,
    order_id: int,
    expect_no: int,
    apply: bool,
    submit: bool,
) -> int:
    order = (
        await session.execute(
            select(LeadOptOrder)
            .where(LeadOptOrder.id == order_id, LeadOptOrder.deleted_at.is_(None))
            .options(selectinload(LeadOptOrder.lines))
        )
    ).scalar_one_or_none()
    if order is None:
        print(f"order_id={order_id}: missing")
        return 1

    print(
        f"\n=== order={order.id} no={order.order_no} (expect no={expect_no}) "
        f"buyer={order.buyer_inn} vol={order.total_volume} lines={len(order.lines)} ==="
    )
    print(f"file={order.source_filename}")
    if order.order_no != expect_no:
        print(f"WARNING: order_no is {order.order_no}, expected {expect_no}")

    lines = sorted(order.lines, key=lambda x: x.line_no)
    if len(lines) < 3:
        print("ERROR: too few lines — abort this order")
        return 2

    # Prefer match known extra keys; else drop last 2 by line_no
    by_known = [
        ln
        for ln in lines
        if (_amt(ln.amount), ln.document_date.isoformat() if ln.document_date else "")
        in KNOWN_EXTRA
    ]
    if len(by_known) == 2:
        remove = by_known
        mode = "known-amount/date"
    else:
        remove = lines[-2:]
        mode = "last-2-by-line_no"
        print(f"NOTE: known extras found={len(by_known)} — using {mode}")

    remove_ids = {ln.id for ln in remove}
    keep = [ln for ln in lines if ln.id not in remove_ids]

    for ln in lines:
        mark = "REMOVE" if ln.id in remove_ids else "KEEP"
        print(
            f"  {mark} L{ln.line_no} {ln.supplier_inn} {ln.document_date} "
            f"{_amt(ln.amount)} doc={ln.document_number}"
        )

    keep_vol = sum((_amt(ln.amount) for ln in keep), Decimal("0"))
    print(f"mode={mode} after: lines={len(keep)} vol={keep_vol}")

    if not apply:
        print("dry-run")
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

    if submit:
        order.status = "queued"
        order.submission_error = None
        await session.flush()
        await enqueue_opt_submit(order.id)
        print(f"APPLIED+QUEUED vol={order.total_volume} lines={len(order.lines)}")
    else:
        order.status = "submitted"
        print(f"APPLIED CRM-only vol={order.total_volume} lines={len(order.lines)}")
    return 0


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--submit", action="store_true")
    args = parser.parse_args()
    if not args.apply:
        args.dry_run = True

    sf = get_session_factory()
    async with sf() as session:
        repo = OptOrderRepository(session)
        code = 0
        for t in TARGETS:
            code = max(
                code,
                await _fix_one(
                    session,
                    repo,
                    order_id=t["order_id"],
                    expect_no=t["order_no"],
                    apply=args.apply and not args.dry_run,
                    submit=args.submit,
                ),
            )
        if args.apply and not args.dry_run:
            await session.commit()
            print("\ncommitted")
    return code


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
