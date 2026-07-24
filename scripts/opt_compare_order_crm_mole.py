#!/usr/bin/env python3
"""Compare CRM OPT order lines vs Mole GET (and optional Excel doc list).

Usage:
  docker exec crm-staging-api python /app/scripts/opt_compare_order_crm_mole.py --order-id 253
  docker exec crm-staging-api python /app/scripts/opt_compare_order_crm_mole.py --order-ids 178,179,253
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.modules.db.models.lead_opt_order import LeadOptOrder
from app.modules.leads.opt.mole_client import get_order
from app.shared.db import get_session_factory


def _amt(v: object) -> Decimal:
    return Decimal(str(v or 0)).quantize(Decimal("0.01"))


def _mole_sum(body: dict[str, Any]) -> Decimal | None:
    for key in ("СуммаИтого", "Сумма", "Итого", "Total"):
        if key in body and body[key] is not None:
            try:
                return _amt(body[key])
            except Exception:
                return None
    return None


def _registry(body: dict[str, Any]) -> list[dict[str, Any]]:
    raw = body.get("Реестр") or body.get("Registry") or []
    return [r for r in raw if isinstance(r, dict)]


async def _one(oid: int) -> int:
    sf = get_session_factory()
    async with sf() as session:
        order = (
            await session.execute(
                select(LeadOptOrder)
                .where(LeadOptOrder.id == oid)
                .options(selectinload(LeadOptOrder.lines))
            )
        ).scalar_one_or_none()
        if order is None:
            print(f"order {oid}: missing")
            return 1

        crm_vol = _amt(order.total_volume)
        print(f"\n=== CRM order={order.id} no={order.order_no} crm={order.crm_id} ===")
        print(f"status={order.status} vol={crm_vol} lines={len(order.lines)}")
        for ln in sorted(order.lines, key=lambda x: x.line_no):
            print(
                f"  L{ln.line_no} {ln.crm_id} {ln.supplier_inn} "
                f"{ln.document_date} { _amt(ln.amount) } doc={ln.document_number}"
            )

        try:
            body = await get_order(order.crm_id)
        except Exception as exc:  # noqa: BLE001
            print(f"MOLE GET FAIL: {exc}")
            return 2

        msum = _mole_sum(body)
        reg = _registry(body)
        print(f"\n--- Mole GET ---")
        print(f"sum={msum} registry_lines={len(reg)}")
        # header extras
        for k in ("Удален", "Проведен", "Номер", "Период", "CRMid", "Статус"):
            if k in body:
                print(f"  {k}={body.get(k)}")
        if not reg:
            # dump non-registry keys for diagnosis
            keys = sorted(k for k in body.keys() if k not in {"Реестр", "Registry"})
            print(f"  keys={keys}")
            # short dump
            slim = {k: body.get(k) for k in keys}
            print(json.dumps(slim, ensure_ascii=False, default=str)[:2000])
        else:
            for i, r in enumerate(reg, start=1):
                doc = r.get("НомерДокумента") or r.get("DocumentNumber")
                crm_line = r.get("CRMid") or r.get("CrmId")
                amount = r.get("Сумма") or r.get("Amount")
                date = r.get("Дата") or r.get("Date")
                supplier = (r.get("Поставщик") or r.get("Supplier") or {})
                sinn = supplier.get("ИНН") if isinstance(supplier, dict) else None
                print(f"  M{i} {crm_line} inn={sinn} date={date} amount={amount} doc={doc}")

        print("\n--- compare ---")
        print(f"CRM vol={crm_vol} Mole sum={msum} match_vol={msum == crm_vol if msum is not None else False}")
        if reg:
            mole_docs = {
                (str(r.get("НомерДокумента") or r.get("DocumentNumber") or "")).strip().upper()
                for r in reg
            }
            mole_docs.discard("")
            crm_docs = {
                (ln.document_number or "").strip().upper()
                for ln in order.lines
                if ln.document_number
            }
            only_crm = sorted(crm_docs - mole_docs)
            only_mole = sorted(mole_docs - crm_docs)
            both = sorted(crm_docs & mole_docs)
            print(f"docs both={len(both)} only_crm={len(only_crm)} only_mole={len(only_mole)}")
            if only_crm:
                print(f"  only_crm: {only_crm}")
            if only_mole:
                print(f"  only_mole: {only_mole}")
        else:
            print("Mole returned NO registry rows — cannot compare document numbers line-by-line.")
            if msum == 0 or msum is None:
                print("CONCLUSION: order shell in Mole empty/zero; CRM+Excel numbers are source of truth for tax.")
            elif msum == crm_vol:
                print("CONCLUSION: sums match but no line registry in API response.")
            else:
                print("CONCLUSION: sum mismatch and no registry — needs 1C admin check.")
    return 0


async def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--order-id", type=int)
    p.add_argument("--order-ids", default="")
    args = p.parse_args()
    ids: list[int] = []
    if args.order_id:
        ids.append(args.order_id)
    ids.extend(int(x) for x in args.order_ids.split(",") if x.strip())
    if not ids:
        print("pass --order-id or --order-ids")
        return 1
    code = 0
    for oid in ids:
        code = max(code, await _one(oid))
    return code


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
