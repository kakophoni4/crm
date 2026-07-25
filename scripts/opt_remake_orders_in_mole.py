#!/usr/bin/env python3
"""Recreate repaired OPT orders in Mole via DELETE + POST.

Use when PUT does not change СуммаИтого (Mole no-op on existing docs).
WARNING: Mole will issue NEW document numbers. Old РС-* are lost.

Usage:
  docker exec crm-staging-api python /app/scripts/opt_remake_orders_in_mole.py --dry-run
  docker exec crm-staging-api python /app/scripts/opt_remake_orders_in_mole.py --ids 178,179,249,250
  docker exec crm-staging-api python /app/scripts/opt_remake_orders_in_mole.py --ids 253 --yes
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.modules.db.models.lead_opt_order import LeadOptOrder
from app.modules.leads.opt.mole_client import delete_order, get_order, post_opt_order
from app.modules.leads.opt.service import OptOrderService
from app.shared.db import get_session_factory

DEFAULT_IDS = [178, 179, 249, 250, 253]


def _sum_get(body: dict) -> float:
    for key in ("СуммаИтого", "Сумма", "Итого", "Total"):
        if key in body and body[key] is not None:
            try:
                return float(body[key])
            except (TypeError, ValueError):
                pass
    return 0.0


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ids", default=",".join(str(i) for i in DEFAULT_IDS))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Actually DELETE+POST (without this flag only dry-run style check)",
    )
    args = parser.parse_args()
    ids = [int(x.strip()) for x in args.ids.split(",") if x.strip()]
    apply = args.yes and not args.dry_run

    sf = get_session_factory()
    async with sf() as session:
        service = OptOrderService(session)
        for oid in ids:
            result = await session.execute(
                select(LeadOptOrder)
                .where(LeadOptOrder.id == oid)
                .options(selectinload(LeadOptOrder.lines)),
            )
            order = result.scalar_one_or_none()
            if order is None:
                print(f"order={oid}: missing")
                continue

            await service._ensure_order_requisites(order)
            payload = service._build_mole_payload(order)
            crm_vol = float(order.total_volume or 0)
            existing_docs = [
                (ln.line_no, ln.document_number)
                for ln in sorted(order.lines, key=lambda x: x.line_no)
                if ln.document_number
            ]

            try:
                before = await get_order(order.crm_id)
                before_sum = _sum_get(before)
            except Exception as exc:
                before_sum = -1.0
                print(f"order={oid}: GET before fail: {exc}")

            print(
                f"order={oid} no={order.order_no} crm={order.crm_id} "
                f"lines={len(order.lines)} crm_vol={crm_vol} mole_sum={before_sum} "
                f"crm_docs={len(existing_docs)}"
            )
            if existing_docs:
                print(f"  WARNING existing CRM doc numbers will be overwritten: {existing_docs}")

            if not apply:
                print("  dry-run / no --yes: skip DELETE+POST")
                continue

            try:
                await delete_order(order.crm_id)
                print("  DELETE ok")
            except Exception as exc:
                print(f"  DELETE: {exc} (continue to POST)")

            try:
                response = await post_opt_order(payload)
            except Exception as exc:
                print(f"  POST FAIL: {exc}")
                continue

            line_numbers = service._extract_line_numbers(response)
            print(f"  POST doc numbers: {len(line_numbers)}/{len(order.lines)}")
            for line in order.lines:
                doc = line_numbers.get(line.crm_id)
                if doc:
                    line.document_number = doc
                    print(f"    L{line.line_no} {line.crm_id} -> {doc}")
                else:
                    print(f"    L{line.line_no} {line.crm_id} -> (none)")

            order.status = "submitted"
            order.submission_error = None
            order.submission_request = payload
            order.submission_response = response
            await session.commit()

            try:
                after = await get_order(order.crm_id)
                print(f"  GET after sum={_sum_get(after)} (crm={crm_vol})")
            except Exception as exc:
                print(f"  GET after fail: {exc}")

    print("DONE" + ("" if apply else " (dry-run)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
