#!/usr/bin/env python3
"""Recalc OPT commission_due with fixed per-unit rates.

Usage:
  # one buyer (dry-run)
  docker exec crm-staging-api python /app/scripts/opt_recalc_order_pricing.py \\
    --buyer-inn 2540258505

  # all orders that contain Кохер — show only delta != 0
  docker exec crm-staging-api python /app/scripts/opt_recalc_order_pricing.py \\
    --supplier-inn 7734474261 --only-changed

  # apply those
  docker exec crm-staging-api python /app/scripts/opt_recalc_order_pricing.py \\
    --supplier-inn 7734474261 --only-changed --apply
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
from app.modules.leads.opt.repository import OptOrderRepository
from app.shared.db import get_session_factory


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--order-id", type=int)
    parser.add_argument("--buyer-inn", default="")
    parser.add_argument("--supplier-inn", default="")
    parser.add_argument("--only-changed", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--limit", type=int, default=500)
    args = parser.parse_args()

    sf = get_session_factory()
    async with sf() as session:
        # Resolve order ids first (no expired-instance / greenlet issues after rollback).
        id_q = select(LeadOptOrder.id).where(LeadOptOrder.deleted_at.is_(None))
        if args.order_id:
            id_q = id_q.where(LeadOptOrder.id == args.order_id)
        if args.buyer_inn:
            id_q = id_q.where(LeadOptOrder.buyer_inn == args.buyer_inn.strip())
        if args.supplier_inn:
            id_q = (
                id_q.join(LeadOptOrderLine, LeadOptOrderLine.order_id == LeadOptOrder.id)
                .where(LeadOptOrderLine.supplier_inn == args.supplier_inn.strip())
                .distinct()
            )
        id_q = id_q.order_by(LeadOptOrder.id.desc()).limit(args.limit)
        order_ids = list((await session.execute(id_q)).scalars().all())

    if not order_ids:
        print("no orders")
        return 1

    print(f"candidates={len(order_ids)}")
    changed_n = 0
    unchanged_n = 0

    for oid in order_ids:
        async with sf() as session:
            repo = OptOrderRepository(session)
            order = (
                await session.execute(
                    select(LeadOptOrder)
                    .where(LeadOptOrder.id == oid)
                    .options(selectinload(LeadOptOrder.lines))
                )
            ).scalar_one_or_none()
            if order is None:
                continue

            old_due = Decimal(str(order.commission_due or 0)).quantize(Decimal("0.01"))
            await repo.apply_pricing_snapshot(order)
            new_due = Decimal(str(order.commission_due or 0)).quantize(Decimal("0.01"))
            delta = (new_due - old_due).quantize(Decimal("0.01"))

            if args.only_changed and delta == 0:
                unchanged_n += 1
                if not args.apply:
                    await session.rollback()
                continue

            changed_n += 1
            print(
                f"order={order.id} no={order.order_no} lead={order.lead_id} "
                f"buyer={order.buyer_inn} vol={order.total_volume} "
                f"due {old_due} -> {new_due} delta={delta}"
            )
            print(f"  breakdown={order.volume_by_category}")
            if args.supplier_inn or args.buyer_inn or args.order_id:
                inns = sorted({ln.supplier_inn for ln in order.lines})
                units = await repo.get_units_by_inns(inns)
                for inn in inns:
                    u = units.get(inn)
                    print(
                        f"  unit {inn}: cat={getattr(u, 'category_code', None)} "
                        f"rate={getattr(u, 'commission_rate_percent', None)} "
                        f"name={getattr(u, 'name', None)}"
                    )

            if args.apply:
                await session.commit()
                print("  applied")
            else:
                await session.rollback()
                print("  dry-run")

    print(f"done changed={changed_n} skipped_unchanged={unchanged_n} apply={args.apply}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
