#!/usr/bin/env python3
"""Reconcile accountant Excel ↔ CRM ↔ Mole for Таврида truncated orders.

Rules (user):
  1) Everything in the Excel keeps those exact document numbers — never remake those
     Mole orders / never overwrite filed numbers with new ones.
  2) Only lines NOT in the Excel are split into a NEW remainder order and POSTed to 1C.

Usage:
  docker cp /root/tavrida.xlsx crm-staging-api:/tmp/tavrida.xlsx
  docker cp scripts/opt_reconcile_accountant_crm_mole.py crm-staging-api:/app/scripts/

  # 1) report Excel vs CRM vs Mole (no writes)
  docker exec crm-staging-api python /app/scripts/opt_reconcile_accountant_crm_mole.py \\
    --xlsx /tmp/tavrida.xlsx --order-ids 178,179,253

  # 2) write Excel document numbers onto KEEP lines; also match other lead orders
  docker exec crm-staging-api python /app/scripts/opt_reconcile_accountant_crm_mole.py \\
    --xlsx /tmp/tavrida.xlsx --order-ids 178,179,253 --lead-id 363 --apply-docs

  # 3) split SEND lines into new remainder order + queue 1C submit (dry-run first)
  docker exec crm-staging-api python /app/scripts/opt_reconcile_accountant_crm_mole.py \\
    --xlsx /tmp/tavrida.xlsx --order-ids 178,179,253 --split-send --dry-run

  docker exec crm-staging-api python /app/scripts/opt_reconcile_accountant_crm_mole.py \\
    --xlsx /tmp/tavrida.xlsx --order-ids 178,179,253 --split-send --submit-remainder
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

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

import importlib.util

from app.modules.db.models.lead_opt_order import LeadOptOrder, LeadOptOrderLine
from app.modules.leads.opt.mole_client import get_order
from app.modules.leads.opt.queue import enqueue_opt_submit
from app.modules.leads.opt.repository import OptOrderRepository
from app.shared.db import get_session_factory


def _load_match_mod() -> Any:
    match_path = Path(__file__).resolve().parent / "opt_match_accountant_registry.py"
    spec = importlib.util.spec_from_file_location("opt_match_accountant_registry", match_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {match_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_match = _load_match_mod()
AccRow = _match.AccRow
_key = _match._key
parse_accountant_xlsx = _match.parse_accountant_xlsx


def _sum_mole(body: dict[str, Any]) -> float | None:
    for key in ("СуммаИтого", "Сумма", "Итого", "Total"):
        if key in body and body[key] is not None:
            try:
                return float(body[key])
            except (TypeError, ValueError):
                return None
    return None


def _amt(v: object) -> Decimal:
    return Decimal(str(v or 0)).quantize(Decimal("0.01"))


async def _classify_order(
    order: LeadOptOrder,
    by_key: dict[str, list[AccRow]],
    used: set[tuple[str, int]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    keep: list[dict[str, Any]] = []
    send: list[dict[str, Any]] = []
    for line in sorted(order.lines, key=lambda x: x.line_no):
        k = _key(line.supplier_inn, line.document_date, _amt(line.amount))
        pick: AccRow | None = None
        for cand in by_key.get(k, []):
            uid = (cand.sheet, cand.row)
            if uid in used:
                continue
            pick = cand
            used.add(uid)
            break
        item = {
            "line_id": line.id,
            "line_no": line.line_no,
            "crm_id": line.crm_id,
            "supplier_inn": line.supplier_inn,
            "date": line.document_date.isoformat() if line.document_date else None,
            "amount": float(_amt(line.amount)),
            "crm_doc": line.document_number,
        }
        if pick is None:
            item["status"] = "SEND"
            send.append(item)
        else:
            item["status"] = "KEEP"
            item["acc_doc"] = pick.document_number
            item["doc_mismatch"] = (
                (line.document_number or "").strip().upper()
                != (pick.document_number or "").strip().upper()
            )
            keep.append(item)
    return keep, send


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--xlsx", required=True)
    parser.add_argument("--order-ids", default="178,179,253")
    parser.add_argument("--lead-id", type=int, default=None)
    parser.add_argument("--apply-docs", action="store_true")
    parser.add_argument("--split-send", action="store_true")
    parser.add_argument("--submit-remainder", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--out", default="/tmp/tavrida_reconcile.json")
    args = parser.parse_args()

    path = Path(args.xlsx)
    if not path.is_file():
        print(f"FILE NOT FOUND: {path}")
        return 1

    order_ids = [int(x) for x in args.order_ids.split(",") if x.strip()]
    acc_rows = parse_accountant_xlsx(path)
    by_key: dict[str, list[AccRow]] = {}
    for ar in acc_rows:
        by_key.setdefault(_key(ar.supplier_inn, ar.document_date, ar.amount), []).append(ar)

    print(f"xlsx={path} accountant_rows={len(acc_rows)}")
    used: set[tuple[str, int]] = set()
    report: dict[str, Any] = {"orders": [], "remainder": None, "extra_lead_applied": 0}

    sf = get_session_factory()
    async with sf() as session:
        repo = OptOrderRepository(session)
        result = await session.execute(
            select(LeadOptOrder)
            .where(LeadOptOrder.id.in_(order_ids), LeadOptOrder.deleted_at.is_(None))
            .options(selectinload(LeadOptOrder.lines))
            .order_by(LeadOptOrder.order_no)
        )
        orders = list(result.scalars().all())

        for order in orders:
            keep, send = await _classify_order(order, by_key, used)
            keep_vol = sum((_amt(x["amount"]) for x in keep), Decimal("0"))
            send_vol = sum((_amt(x["amount"]) for x in send), Decimal("0"))
            crm_vol = _amt(order.total_volume)

            mole_sum: float | None = None
            mole_err: str | None = None
            try:
                body = await get_order(order.crm_id)
                mole_sum = _sum_mole(body)
            except Exception as exc:  # noqa: BLE001
                mole_err = str(exc)[:300]

            mismatches = [k for k in keep if k.get("doc_mismatch")]
            mole_vs_keep = None
            if mole_sum is not None:
                mole_vs_keep = abs(Decimal(str(mole_sum)) - keep_vol) < Decimal("0.02")

            row = {
                "id": order.id,
                "order_no": order.order_no,
                "crm_id": order.crm_id,
                "file": order.source_filename,
                "crm_vol": float(crm_vol),
                "keep_n": len(keep),
                "keep_vol": float(keep_vol),
                "send_n": len(send),
                "send_vol": float(send_vol),
                "mole_sum": mole_sum,
                "mole_err": mole_err,
                "mole_matches_keep_vol": mole_vs_keep,
                "doc_mismatches": len(mismatches),
                "keep": keep,
                "send": send,
            }
            report["orders"].append(row)

            print(
                f"\n=== order={order.id} no={order.order_no} crm={order.crm_id} ==="
            )
            print(
                f"CRM vol={crm_vol} | KEEP {len(keep)}/{keep_vol} | "
                f"SEND {len(send)}/{send_vol} | Mole={mole_sum} "
                f"mole≈keep={mole_vs_keep} doc_fix_needed={len(mismatches)}"
            )
            for k in keep:
                flag = " FIX_DOC" if k.get("doc_mismatch") else ""
                print(
                    f"  KEEP L{k['line_no']} {k['supplier_inn']} {k['date']} "
                    f"{k['amount']} crm={k['crm_doc']} excel={k.get('acc_doc')}{flag}"
                )
            for s in send:
                print(
                    f"  SEND L{s['line_no']} {s['supplier_inn']} {s['date']} "
                    f"{s['amount']} crm_doc={s['crm_doc']}"
                )

            if args.apply_docs and not args.dry_run:
                for k in keep:
                    line = next(ln for ln in order.lines if ln.id == k["line_id"])
                    line.document_number = k["acc_doc"]
                for s in send:
                    # filed numbers must not stick on lines we will re-POST
                    line = next(ln for ln in order.lines if ln.id == s["line_id"])
                    line.document_number = None
                print("  applied Excel docs on KEEP; cleared docs on SEND")

        # Optional: apply Excel docs to OTHER orders on same lead (КП/СД/…)
        if args.lead_id is not None and args.apply_docs:
            extra = await session.execute(
                select(LeadOptOrder)
                .where(
                    LeadOptOrder.lead_id == args.lead_id,
                    LeadOptOrder.deleted_at.is_(None),
                    LeadOptOrder.id.not_in(order_ids),
                )
                .options(selectinload(LeadOptOrder.lines))
            )
            n_extra = 0
            for order in extra.scalars().all():
                for line in order.lines:
                    k = _key(line.supplier_inn, line.document_date, _amt(line.amount))
                    for cand in by_key.get(k, []):
                        uid = (cand.sheet, cand.row)
                        if uid in used:
                            continue
                        if not args.dry_run and cand.document_number:
                            line.document_number = cand.document_number
                            n_extra += 1
                        used.add(uid)
                        break
            report["extra_lead_applied"] = n_extra
            print(f"\nextra lead={args.lead_id} lines got Excel docs: {n_extra}")

        # Split SEND lines → new remainder order
        all_send_line_ids: list[int] = []
        parent_by_line: dict[int, LeadOptOrder] = {}
        for order, row in zip(orders, report["orders"], strict=True):
            for s in row["send"]:
                all_send_line_ids.append(s["line_id"])
                parent_by_line[s["line_id"]] = order

        if args.split_send and all_send_line_ids:
            print(
                f"\n=== SPLIT SEND ({len(all_send_line_ids)} lines) → new remainder order ==="
            )
            if args.dry_run:
                print("dry-run: would move SEND lines to new order and optionally submit")
            else:
                # Use first parent as template (same lead/buyer)
                template = orders[0]
                max_no = (
                    await session.execute(
                        select(func.coalesce(func.max(LeadOptOrder.order_no), 0)).where(
                            LeadOptOrder.lead_id == template.lead_id,
                            LeadOptOrder.deleted_at.is_(None),
                        )
                    )
                ).scalar_one()
                new_order = LeadOptOrder(
                    lead_id=template.lead_id,
                    crm_id=repo.new_crm_id("crm-order"),
                    order_no=int(max_no) + 1,
                    buyer_inn=template.buyer_inn,
                    buyer_kpp=template.buyer_kpp,
                    buyer_name=template.buyer_name,
                    vat_rate_percent=template.vat_rate_percent,
                    period_code=template.period_code,
                    status="draft",
                    source_filename="remainder-after-truncated-bug.xlsx",
                    created_by=template.created_by,
                )
                session.add(new_order)
                await session.flush()

                # Move lines
                send_lines = (
                    await session.execute(
                        select(LeadOptOrderLine).where(
                            LeadOptOrderLine.id.in_(all_send_line_ids)
                        )
                    )
                ).scalars().all()
                for i, ln in enumerate(sorted(send_lines, key=lambda x: (x.order_id, x.line_no)), start=1):
                    ln.order_id = new_order.id
                    ln.line_no = i
                    ln.document_number = None

                await session.flush()

                # Renumber parents + recalc pricing
                for order in orders:
                    await session.refresh(order, attribute_names=["lines"])
                    for i, ln in enumerate(sorted(order.lines, key=lambda x: x.line_no), start=1):
                        ln.line_no = i
                    await session.flush()
                    await session.refresh(order, attribute_names=["lines"])
                    await repo.apply_pricing_snapshot(order)
                    # Parent already filed in tax / Mole keep-vol — do not requeue
                    order.status = "submitted"
                    order.submission_error = None

                await session.refresh(new_order, attribute_names=["lines"])
                await repo.apply_pricing_snapshot(new_order)

                if args.submit_remainder:
                    new_order.status = "queued"
                    await session.commit()
                    await enqueue_opt_submit(new_order.id)
                    print(
                        f"CREATED remainder order_id={new_order.id} no={new_order.order_no} "
                        f"crm={new_order.crm_id} vol={new_order.total_volume} QUEUED→1C"
                    )
                else:
                    await session.commit()
                    print(
                        f"CREATED remainder order_id={new_order.id} no={new_order.order_no} "
                        f"crm={new_order.crm_id} vol={new_order.total_volume} (not queued; "
                        f"pass --submit-remainder)"
                    )

                report["remainder"] = {
                    "id": new_order.id,
                    "order_no": new_order.order_no,
                    "crm_id": new_order.crm_id,
                    "volume": float(new_order.total_volume or 0),
                    "lines": len(new_order.lines),
                    "queued": bool(args.submit_remainder),
                }
        elif args.apply_docs and not args.dry_run:
            await session.commit()
            print("\ncommitted --apply-docs")

    Path(args.out).write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"\nWrote {args.out}")
    print(
        "\nNEXT: if mole≈keep=True for 12/13 — leave those Mole orders alone. "
        "Only remainder goes to 1C. Order 16 KEEP-only — do not remake even if Mole=0."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
