#!/usr/bin/env python3
"""Restore a CRM OPT order into Mole when GET shows deleted/empty shell.

PUT on Удален=true shells is a no-op in Mole. Same-crm_id DELETE+POST can also
stick to the dead shell (POST returns numbers, GET still sum=0/Удален).

Preferred path when that happens: --fresh-crm-ids (new order+line CRMid, POST).

Usage:
  docker cp scripts/opt_restore_order_to_mole.py crm-staging-api:/app/scripts/

  # check
  docker exec crm-staging-api python /app/scripts/opt_restore_order_to_mole.py --order-id 273

  # after failed remake on dead shell:
  docker exec crm-staging-api python /app/scripts/opt_restore_order_to_mole.py \\
    --order-id 273 --apply --fresh-crm-ids
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
from app.modules.leads.opt.mole_client import (
    delete_order,
    filter_orders,
    get_order,
    post_opt_order,
    put_order,
)
from app.modules.leads.opt.periods import period_code_to_mole_iso
from app.modules.leads.opt.repository import OptOrderRepository
from app.modules.leads.opt.service import OptOrderService
from app.modules.leads.opt.sync_diff import mole_crm_id, mole_is_deleted
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


def _period_for_payload(period_code: str) -> str | None:
    iso = period_code_to_mole_iso(period_code) if period_code else None
    if not iso:
        return None
    # Mole stores datetime; plain date often becomes 0001-01-01 on dead docs.
    if "T" not in iso:
        return f"{iso}T00:00:00"
    return iso


def _dump_header(label: str, body: dict[str, Any]) -> None:
    slim = {k: body.get(k) for k in sorted(body) if k not in {"Реестр", "Registry"}}
    print(f"\n=== {label} ===")
    print(json.dumps(slim, ensure_ascii=False, default=str)[:3000])
    reg = body.get("Реестр") or body.get("Registry") or []
    print(f"registry_lines={len(reg) if isinstance(reg, list) else 0} sum={_sum_get(body)}")


def _build_payload(service: OptOrderService, order: LeadOptOrder, period_code: str) -> dict[str, Any]:
    payload = service._build_mole_payload(order)
    period = _period_for_payload(period_code)
    if period:
        payload["Период"] = period
    return payload


def _filter_row_sum(row: dict[str, Any]) -> Decimal:
    for key in ("СуммаИтого", "Сумма", "Итого", "Total", "volume"):
        if key in row and row[key] is not None:
            try:
                return _amt(row[key])
            except Exception:
                pass
    return Decimal("0.00")


async def _check_in_filter(period_code: str, crm_id: str) -> tuple[bool, Decimal, bool]:
    iso = period_code_to_mole_iso(period_code)
    if not iso:
        return False, Decimal("0.00"), True
    rows = await filter_orders(period_iso=iso)
    for row in rows:
        if mole_crm_id(row) != crm_id:
            continue
        return True, _filter_row_sum(row), mole_is_deleted(row)
    return False, Decimal("0.00"), True


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--order-id", type=int, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--allow-remake",
        action="store_true",
        help="DELETE+POST same crm_id (often fails on dead shells)",
    )
    parser.add_argument(
        "--fresh-crm-ids",
        action="store_true",
        help="Assign new order/line CRMid then POST (recommended after failed remake)",
    )
    parser.add_argument(
        "--skip-put",
        action="store_true",
        help="Skip PUT attempt (use with --fresh-crm-ids / --allow-remake)",
    )
    args = parser.parse_args()

    if args.fresh_crm_ids and not args.apply:
        print("--fresh-crm-ids requires --apply")
        return 1

    sf = get_session_factory()
    async with sf() as session:
        service = OptOrderService(session)
        repo = OptOrderRepository(session)
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
        period_code = (order.period_code or "").strip()
        crm_vol = _amt(order.total_volume)
        old_order_crm = order.crm_id

        print(
            f"CRM order={order.id} no={order.order_no} lead={order.lead_id} "
            f"crm={order.crm_id} status={order.status} period={period_code} "
            f"lines={len(order.lines)} vol={crm_vol}"
        )

        try:
            before = await get_order(order.crm_id)
            _dump_header("GET before (old crm_id)", before)
            print(
                f"verdict_before: deleted={_is_deleted(before)} "
                f"sum={_sum_get(before)} crm={crm_vol}"
            )
        except Exception as exc:  # noqa: BLE001
            print(f"GET before fail: {exc}")
            before = None

        if not args.apply:
            print("\ndry-run. If shell is deleted/empty after failed remake, use:")
            print(
                "  ... --order-id 273 --apply --fresh-crm-ids --skip-put"
            )
            return 0

        # --- fresh CRMid path (bypass dead shell) ---
        if args.fresh_crm_ids:
            print("\n--- FRESH CRM IDs + POST + PUT ---")
            order.crm_id = repo.new_crm_id("crm-order")
            for line in order.lines:
                line.crm_id = repo.new_crm_id("crm-line")
            print(f"new order crm_id: {old_order_crm} -> {order.crm_id}")

            payload = _build_payload(service, order, period_code)
            print(
                f"payload: registry={len(payload.get('Реестр') or [])} "
                f"period={payload.get('Период')}"
            )

            try:
                post_resp = await post_opt_order(payload)
            except Exception as exc:  # noqa: BLE001
                print(f"POST FAIL: {exc}")
                await session.rollback()
                return 4

            print("POST response (trim):")
            print(json.dumps(post_resp, ensure_ascii=False, default=str)[:2500])
            line_numbers = service._extract_line_numbers(post_resp)
            print(f"POST doc numbers: {len(line_numbers)}/{len(order.lines)}")
            if len(line_numbers) != len(order.lines):
                print("ABORT — incomplete POST registry")
                await session.rollback()
                return 4
            for line in sorted(order.lines, key=lambda x: x.line_no):
                old = line.document_number
                new = line_numbers.get(line.crm_id)
                if new:
                    line.document_number = new
                print(f"  L{line.line_no} {old} -> {line.document_number}")

            # Fresh POST often leaves Удален=false but sum=0 / period=0001.
            # PUT on that live shell is what actually fills amounts (PUT on
            # Удален=true shells is a no-op).
            print("\n--- PUT after fresh POST ---")
            try:
                put_resp = await put_order(order.crm_id, payload)
                print(json.dumps(put_resp, ensure_ascii=False, default=str)[:2500])
            except Exception as exc:  # noqa: BLE001
                print(f"PUT FAIL: {exc}")
                put_resp = None

            try:
                final = await get_order(order.crm_id)
            except Exception as exc:  # noqa: BLE001
                print(f"GET after PUT FAIL: {exc}")
                await session.rollback()
                return 5

            _dump_header("GET after POST+PUT", final)
            get_sum = _sum_get(final)
            get_ok = (not _is_deleted(final)) and get_sum == crm_vol

            in_filter, filter_sum, filter_del = await _check_in_filter(period_code, order.crm_id)
            print(
                f"filter period={period_code}: present={in_filter} deleted={filter_del} "
                f"sum={filter_sum} (crm={crm_vol})"
            )
            filter_ok = (
                in_filter and (not filter_del) and filter_sum == crm_vol
            )
            # GET registry is often empty; trust GET/filter totals only.
            final_ok = get_ok or filter_ok
            print(f"verdict_after_fresh: get_ok={get_ok} filter_ok={filter_ok} ok={final_ok}")

            if not final_ok:
                print("ABORT commit — Mole still bad; CRM crm_ids/docs NOT saved")
                await session.rollback()
                return 5

            order.status = "submitted"
            order.submission_error = None
            order.submission_request = payload
            order.submission_response = {
                "post": post_resp,
                "put": put_resp,
                "get": {k: final.get(k) for k in final if k not in {"Реестр", "Registry"}},
            }
            await session.commit()
            print(f"CRM committed with new crm_id={order.crm_id}")
            print(f"Old dead shell left in Mole: {old_order_crm} (ignore / admin purge)")
            return 0

        payload = _build_payload(service, order, period_code)
        print(
            f"payload: registry={len(payload.get('Реестр') or [])} "
            f"period={payload.get('Период')} keys={sorted(payload.keys())}"
        )

        if not args.skip_put:
            print("\n--- PUT ---")
            try:
                put_resp = await put_order(order.crm_id, payload)
                print(json.dumps(put_resp, ensure_ascii=False, default=str)[:2500])
            except Exception as exc:  # noqa: BLE001
                print(f"PUT FAIL: {exc}")
                put_resp = None

            after = await get_order(order.crm_id)
            _dump_header("GET after PUT", after)
            ok = (not _is_deleted(after)) and _sum_get(after) == crm_vol
            print(f"verdict_after_put: ok={ok}")
            if ok:
                order.status = "submitted"
                order.submission_error = None
                order.submission_request = payload
                order.submission_response = put_resp if isinstance(put_resp, dict) else after
                await session.commit()
                print("CRM: submission audit updated; document numbers UNCHANGED")
                return 0

        if not args.allow_remake:
            print(
                "\nPUT did not restore. Prefer:\n"
                "  ... --apply --fresh-crm-ids --skip-put\n"
                "or same-id remake (often fails):\n"
                "  ... --apply --allow-remake --skip-put"
            )
            await session.rollback()
            return 3

        print("\n--- DELETE + POST (same crm_id) ---")
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

        print(json.dumps(post_resp, ensure_ascii=False, default=str)[:4000])
        line_numbers = service._extract_line_numbers(post_resp)
        print(f"POST doc numbers: {len(line_numbers)}/{len(order.lines)}")
        for line in sorted(order.lines, key=lambda x: x.line_no):
            old = line.document_number
            new = line_numbers.get(line.crm_id)
            if new:
                line.document_number = new
            print(f"  L{line.line_no} {old} -> {new or old}")

        final = await get_order(order.crm_id)
        _dump_header("GET after POST", final)
        final_ok = (not _is_deleted(final)) and _sum_get(final) == crm_vol
        print(f"verdict_after_post: ok={final_ok}")
        if not final_ok:
            print(
                "Same-crm_id remake stuck on dead shell. "
                "Rollback CRM doc changes and use --fresh-crm-ids."
            )
            await session.rollback()
            return 5

        order.status = "submitted"
        order.submission_error = None
        order.submission_request = payload
        order.submission_response = post_resp
        await session.commit()
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
