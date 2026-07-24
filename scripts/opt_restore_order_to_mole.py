#!/usr/bin/env python3
"""Verify Mole state for a CRM OPT order and restore it via PUT (keep CRM doc numbers).

Use when GET shows Удален=true / sum=0 / wrong period, but CRM has full registry.

Flow:
  1) GET before
  2) PUT payload (+ Период) — Mole rejects unknown keys like Удален
  3) GET after — require sum ≈ CRM volume and Удален!=true
  4) optional --allow-remake: DELETE+POST if PUT left sum wrong
     WARNING: remake gets NEW 1C doc numbers and writes them into CRM

Usage:
  docker cp scripts/opt_restore_order_to_mole.py crm-staging-api:/app/scripts/
  # check only
  docker exec crm-staging-api python /app/scripts/opt_restore_order_to_mole.py --order-id 273
  # restore
  docker exec crm-staging-api python /app/scripts/opt_restore_order_to_mole.py --order-id 273 --apply
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
from app.modules.leads.opt.mole_client import delete_order, get_order, post_opt_order, put_order
from app.modules.leads.opt.periods import period_code_to_mole_iso
from app.modules.leads.opt.service import OptOrderService
from app.shared.db import get_session_factory


def _amt(v: object) -> Decimal:
    return Decimal(str(v or 0)).quantize(Decimal("0.01"))


def _sum_get(body: dict[str, Any]) -> Decimal:
    for key in ("СуммаИтого", "Сумма", "Итого", "Total"):
        if key in body and body[key] is not None:
            try:
                return _amt(body[key])
            except Exception:
                return Decimal("0.00")
    return Decimal("0.00")


def _is_deleted(body: dict[str, Any]) -> bool:
    raw = body.get("Удален")
    if isinstance(raw, bool):
        return raw
    return str(raw or "").strip().lower() in {"true", "1", "yes", "да"}


def _dump_header(label: str, body: dict[str, Any]) -> None:
    slim = {k: body.get(k) for k in sorted(body) if k not in {"Реестр", "Registry"}}
    print(f"\n=== {label} ===")
    print(json.dumps(slim, ensure_ascii=False, default=str)[:3000])
    reg = body.get("Реестр") or body.get("Registry") or []
    print(f"registry_lines={len(reg) if isinstance(reg, list) else 0} sum={_sum_get(body)}")


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--order-id", type=int, required=True)
    parser.add_argument("--apply", action="store_true", help="PUT (and optional remake) for real")
    parser.add_argument(
        "--allow-remake",
        action="store_true",
        help="If PUT leaves wrong sum: DELETE+POST (NEW doc numbers → CRM)",
    )
    args = parser.parse_args()

    sf = get_session_factory()
    async with sf() as session:
        service = OptOrderService(session)
        order = (
            await session.execute(
                select(LeadOptOrder)
                .where(LeadOptOrder.id == args.order_id)
                .options(selectinload(LeadOptOrder.lines))
            )
        ).scalar_one_or_none()
        if order is None:
            print(f"order {args.order_id}: not found")
            return 1
        if order.deleted_at is not None:
            print(f"order {args.order_id}: soft-deleted in CRM — abort")
            return 1

        await service._ensure_order_requisites(order)
        payload = service._build_mole_payload(order)
        period_code = (order.period_code or "").strip()
        iso = period_code_to_mole_iso(period_code) if period_code else None
        if iso:
            payload["Период"] = iso
        # Mole PUT rejects unknown keys like Удален — never send it.

        crm_vol = _amt(order.total_volume)
        docs = sum(1 for ln in order.lines if ln.document_number)
        print(
            f"CRM order={order.id} no={order.order_no} lead={order.lead_id} "
            f"crm={order.crm_id} status={order.status} period={period_code} "
            f"lines={len(order.lines)} docs={docs} vol={crm_vol}"
        )
        print(f"payload: registry={len(payload.get('Реестр') or [])} period={payload.get('Период')}")
        print(f"payload keys={sorted(payload.keys())}")

        before = await get_order(order.crm_id)
        _dump_header("GET before", before)
        before_sum = _sum_get(before)
        before_del = _is_deleted(before)
        print(
            f"verdict_before: deleted={before_del} sum_match={before_sum == crm_vol} "
            f"(mole={before_sum} crm={crm_vol})"
        )

        if not args.apply:
            print("\ndry-run: pass --apply to PUT restore")
            if before_del or before_sum != crm_vol:
                print("expected: PUT with Реестр + Период (no Удален key — Mole rejects it)")
            return 0

        print("\n--- PUT ---")
        try:
            put_resp = await put_order(order.crm_id, payload)
            print(json.dumps(put_resp, ensure_ascii=False, default=str)[:2500])
        except Exception as exc:  # noqa: BLE001
            print(f"PUT FAIL: {exc}")
            return 2

        after = await get_order(order.crm_id)
        _dump_header("GET after PUT", after)
        after_sum = _sum_get(after)
        after_del = _is_deleted(after)
        ok = (not after_del) and after_sum == crm_vol
        print(f"verdict_after_put: deleted={after_del} sum_match={after_sum == crm_vol} ok={ok}")

        if ok:
            # Keep CRM document_number; only refresh audit blobs.
            order.status = "submitted"
            order.submission_error = None
            order.submission_request = payload
            order.submission_response = put_resp if isinstance(put_resp, dict) else after
            await session.commit()
            print("CRM: submission audit updated; document numbers UNCHANGED")
            return 0

        if not args.allow_remake:
            print(
                "\nPUT did not fully restore. Re-run with --allow-remake to DELETE+POST "
                "(WARNING: new 1C doc numbers will overwrite CRM)."
            )
            await session.rollback()
            return 3

        print("\n--- DELETE + POST (remake) ---")
        print("WARNING: Mole will assign NEW document numbers")
        try:
            await delete_order(order.crm_id)
            print("DELETE ok")
        except Exception as exc:  # noqa: BLE001
            print(f"DELETE: {exc} (continue POST)")

        try:
            post_resp = await post_opt_order(payload)
        except Exception as exc:  # noqa: BLE001
            print(f"POST FAIL: {exc}")
            await session.rollback()
            return 4

        line_numbers = service._extract_line_numbers(post_resp)
        print(f"POST doc numbers: {len(line_numbers)}/{len(order.lines)}")
        for line in sorted(order.lines, key=lambda x: x.line_no):
            old = line.document_number
            new = line_numbers.get(line.crm_id)
            if new:
                line.document_number = new
            print(f"  L{line.line_no} {old} -> {new or old}")

        order.status = "submitted"
        order.submission_error = None
        order.submission_request = payload
        order.submission_response = post_resp
        await session.commit()

        final = await get_order(order.crm_id)
        _dump_header("GET after POST", final)
        final_ok = (not _is_deleted(final)) and _sum_get(final) == crm_vol
        print(f"verdict_after_post: ok={final_ok}")
        return 0 if final_ok else 5


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
