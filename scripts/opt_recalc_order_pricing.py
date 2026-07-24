#!/usr/bin/env python3
"""Recalc OPT commission_due with fixed per-unit rates (Кохер 2.8% etc).

Usage:
  docker exec crm-staging-api python /app/scripts/opt_recalc_order_pricing.py --buyer-inn 2540258505
  docker exec crm-staging-api python /app/scripts/opt_recalc_order_pricing.py --order-id 123 --apply
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

from app.modules.db.models.lead_opt_order import LeadOptOrder
from app.modules.leads.opt.repository import OptOrderRepository
from app.shared.db import get_session_factory


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--order-id", type=int)
    parser.add_argument("--buyer-inn", default="")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    sf = get_session_factory()
    async with sf() as session:
        repo = OptOrderRepository(session)
        q = (
            select(LeadOptOrder)
            .where(LeadOptOrder.deleted_at.is_(None))
            .options(selectinload(LeadOptOrder.lines))
            .order_by(LeadOptOrder.id.desc())
        )
        if args.order_id:
            q = q.where(LeadOptOrder.id == args.order_id)
        if args.buyer_inn:
            q = q.where(LeadOptOrder.buyer_inn == args.buyer_inn.strip())
        orders = list((await session.execute(q.limit(20))).scalars().all())
        if not orders:
            print("no orders")
            return 1

        for order in orders:
            old_due = Decimal(str(order.commission_due or 0))
            old_br = dict(order.volume_by_category or {})
            await repo.apply_pricing_snapshot(order)
            new_due = Decimal(str(order.commission_due or 0))
            print(
                f"order={order.id} no={order.order_no} lead={order.lead_id} "
                f"vol={order.total_volume} due {old_due} -> {new_due} "
                f"delta={new_due - old_due}"
            )
            print(f"  breakdown={order.volume_by_category}")
            inns = sorted({ln.supplier_inn for ln in order.lines})
            units = await repo.get_units_by_inns(inns)
            for inn in inns:
                u = units.get(inn)
                print(
                    f"  unit {inn}: cat={getattr(u, 'category_code', None)} "
                    f"rate={getattr(u, 'commission_rate_percent', None)} "
                    f"name={getattr(u, 'name', None)}"
                )
            if not args.apply:
                # rollback in-memory by not committing; re-read would be needed —
                # for dry-run just don't commit and expire
                await session.rollback()
                print("  dry-run (rolled back)")
            else:
                await session.commit()
                print("  applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
