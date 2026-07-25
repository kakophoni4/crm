"""Diagnose Mole PUT/POST for repaired OPT orders (print raw responses).

Usage:
  docker exec crm-staging-api python /app/scripts/opt_diagnose_mole_put.py --order-id 178
  docker exec crm-staging-api python /app/scripts/opt_diagnose_mole_put.py --order-id 178 --try-delete-post
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.modules.db.models.lead_opt_order import LeadOptOrder
from app.modules.leads.opt.mole_client import (
    delete_order,
    get_order,
    post_opt_order,
    put_order,
)
from app.modules.leads.opt.periods import period_code_to_mole_iso
from app.modules.leads.opt.service import OptOrderService
from app.shared.db import get_session_factory


def _dump(label: str, obj: object) -> None:
    print(f"\n=== {label} ===")
    try:
        print(json.dumps(obj, ensure_ascii=False, indent=2, default=str)[:8000])
    except Exception:
        print(repr(obj)[:8000])


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
    parser.add_argument("--order-id", type=int, required=True)
    parser.add_argument(
        "--try-delete-post",
        action="store_true",
        help="If PUT does not change sum: DELETE then POST (new Mole doc)",
    )
    parser.add_argument(
        "--with-period",
        action="store_true",
        help="Add Период ISO to payload",
    )
    parser.add_argument(
        "--apply-db",
        action="store_true",
        help="After successful POST, write new document numbers into CRM",
    )
    args = parser.parse_args()

    sf = get_session_factory()
    async with sf() as session:
        service = OptOrderService(session)
        result = await session.execute(
            select(LeadOptOrder)
            .where(LeadOptOrder.id == args.order_id)
            .options(selectinload(LeadOptOrder.lines))
            .limit(1)
        )
        order = result.scalar_one_or_none()
        if order is None:
            print(f"order {args.order_id} not found")
            return 1

        await service._ensure_order_requisites(order)
        payload = service._build_mole_payload(order)
        if args.with_period and order.period:
            iso = period_code_to_mole_iso(order.period)
            if iso:
                payload["Период"] = iso

        crm_vol = float(order.total_volume or 0)
        print(
            f"order={order.id} no={order.order_no} crm={order.crm_id} "
            f"period={order.period} lines={len(order.lines)} vol={crm_vol}"
        )
        print(f"payload registry lines={len(payload.get('Реестр') or [])}")

        before = await get_order(order.crm_id)
        _dump("GET before", before)
        print(f"GET before sum={_sum_get(before)}")

        try:
            put_resp = await put_order(order.crm_id, payload)
            _dump("PUT response", put_resp)
        except Exception as exc:
            print(f"PUT FAIL: {exc}")
            put_resp = None

        after_put = await get_order(order.crm_id)
        print(f"GET after PUT sum={_sum_get(after_put)}")
        _dump(
            "GET after PUT (keys)",
            {k: after_put.get(k) for k in sorted(after_put) if k not in ("Реестр", "Registry")},
        )
        reg = after_put.get("Реестр") or after_put.get("Registry")
        print(
            f"GET after PUT has registry={isinstance(reg, list)} "
            f"len={len(reg) if isinstance(reg, list) else 0}"
        )

        need_recreate = abs(_sum_get(after_put) - crm_vol) > 0.01
        if args.try_delete_post and need_recreate:
            print("\n--- try DELETE + POST ---")
            try:
                del_resp = await delete_order(order.crm_id)
                _dump("DELETE response", del_resp)
            except Exception as exc:
                print(f"DELETE FAIL: {exc}")

            try:
                post_resp = await post_opt_order(payload)
                _dump("POST response", post_resp)
                line_numbers = service._extract_line_numbers(post_resp)
                print(f"POST doc numbers: {len(line_numbers)}/{len(order.lines)}")
                for cid, num in sorted(line_numbers.items()):
                    print(f"  {cid} -> {num}")
                if args.apply_db:
                    for line in order.lines:
                        doc = line_numbers.get(line.crm_id)
                        if doc:
                            line.document_number = doc
                    order.status = "submitted"
                    order.submission_error = None
                    order.submission_request = payload
                    order.submission_response = post_resp
                    await session.commit()
                    print("CRM updated with POST response")
            except Exception as exc:
                print(f"POST FAIL: {exc}")

            after_post = await get_order(order.crm_id)
            print(f"GET after POST sum={_sum_get(after_post)} (crm={crm_vol})")
            _dump("GET after POST", after_post)

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
