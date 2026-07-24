#!/usr/bin/env python3
"""Compare DOCUMENT NUMBERS: Excel / CRM / Mole filter / last 1C submit response.

GET /orders/{id} often has NO Реестр — use filter + submission_response instead.

Usage:
  docker exec crm-staging-api python /app/scripts/opt_compare_doc_numbers.py \\
    --xlsx /tmp/tavrida.xlsx --order-ids 178,179,253 --period 2/26
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.modules.db.models.lead_opt_order import LeadOptOrder
from app.modules.leads.opt.mole_client import filter_orders
from app.modules.leads.opt.periods import period_code_to_mole_iso
from app.modules.leads.opt.sync_diff import mole_crm_id
from app.shared.db import get_session_factory

import importlib.util


def _load_match() -> Any:
    name = "opt_match_accountant_registry"
    if name in sys.modules:
        return sys.modules[name]
    path = Path(__file__).resolve().parent / "opt_match_accountant_registry.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _norm_doc(v: object) -> str:
    return str(v or "").strip().upper().replace("Ё", "Е")


def _registry(row: dict[str, Any]) -> list[dict[str, Any]]:
    raw = row.get("Реестр") or row.get("Registry") or []
    if not isinstance(raw, list):
        return []
    return [x for x in raw if isinstance(x, dict)]


def _docs_from_registry(reg: list[dict[str, Any]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for item in reg:
        doc = _norm_doc(item.get("НомерДокумента") or item.get("DocumentNumber"))
        if not doc:
            continue
        supplier = item.get("Поставщик") or item.get("Supplier") or {}
        sinn = ""
        if isinstance(supplier, dict):
            sinn = str(supplier.get("ИНН") or supplier.get("INN") or "").strip()
        date = str(
            item.get("ДатаДокумента")
            or item.get("DocumentDate")
            or item.get("Дата")
            or ""
        )[:10]
        amount = str(item.get("Сумма") or item.get("Amount") or "")
        out.append(
            {
                "doc": doc,
                "line_crm": str(mole_crm_id(item) or ""),
                "supplier_inn": sinn,
                "date": date,
                "amount": amount,
            }
        )
    return out


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--xlsx", default="/tmp/tavrida.xlsx")
    parser.add_argument("--order-ids", default="178,179,253")
    parser.add_argument("--period", default="2/26")
    args = parser.parse_args()

    order_ids = [int(x) for x in args.order_ids.split(",") if x.strip()]
    match = _load_match()
    excel_docs: dict[str, dict[str, Any]] = {}
    xlsx = Path(args.xlsx)
    if xlsx.is_file():
        for ar in match.parse_accountant_xlsx(xlsx):
            if not ar.document_number:
                continue
            d = _norm_doc(ar.document_number)
            excel_docs[d] = {
                "supplier_inn": ar.supplier_inn,
                "date": ar.document_date.isoformat() if ar.document_date else None,
                "amount": float(ar.amount) if ar.amount is not None else None,
            }
        print(f"Excel docs: {len(excel_docs)}")
    else:
        print(f"Excel missing: {xlsx} (skip excel side)")

    iso = period_code_to_mole_iso(args.period)
    if not iso:
        print(f"bad period {args.period}")
        return 1
    print(f"Mole filter period={args.period} iso={iso} ...")
    mole_rows = await filter_orders(period_iso=iso)
    print(f"Mole filter orders: {len(mole_rows)}")

    # index: order crm_id -> docs; also global doc -> which mole order
    mole_by_order: dict[str, list[dict[str, str]]] = {}
    mole_doc_owner: dict[str, str] = {}
    mole_with_reg = 0
    for row in mole_rows:
        ocid = mole_crm_id(row) or ""
        docs = _docs_from_registry(_registry(row))
        if docs:
            mole_with_reg += 1
            mole_by_order[ocid] = docs
            for d in docs:
                mole_doc_owner[d["doc"]] = ocid
    print(f"Mole orders that include Реестр with doc numbers: {mole_with_reg}")

    sf = get_session_factory()
    async with sf() as session:
        for oid in order_ids:
            order = (
                await session.execute(
                    select(LeadOptOrder)
                    .where(LeadOptOrder.id == oid)
                    .options(selectinload(LeadOptOrder.lines))
                )
            ).scalar_one_or_none()
            if order is None:
                print(f"\norder {oid}: missing")
                continue

            crm_docs = []
            for ln in sorted(order.lines, key=lambda x: x.line_no):
                doc = _norm_doc(ln.document_number)
                crm_docs.append(
                    {
                        "line_no": ln.line_no,
                        "doc": doc,
                        "supplier_inn": ln.supplier_inn,
                        "date": ln.document_date.isoformat() if ln.document_date else None,
                        "amount": float(ln.amount or 0),
                        "line_crm": ln.crm_id,
                    }
                )

            submit_docs = _docs_from_registry(
                _registry(order.submission_response)
                if isinstance(order.submission_response, dict)
                else []
            )

            mole_docs = mole_by_order.get(order.crm_id, [])

            print(f"\n======== order={order.id} no={order.order_no} crm={order.crm_id} ========")
            print(f"CRM lines={len(crm_docs)} submit_response_docs={len(submit_docs)} mole_filter_docs={len(mole_docs)}")

            print("\n-- DOC NUMBERS side by side --")
            print(f"{'L':>2} {'CRM_DOC':<16} {'EXCEL':<16} {'MOLE_FILTER':<16} {'SUBMIT_1C':<16} verdict")
            for row in crm_docs:
                doc = row["doc"]
                in_excel = doc in excel_docs if doc else False
                in_mole = any(d["doc"] == doc for d in mole_docs) if doc else False
                # also: doc exists in Mole under ANY order
                mole_owner = mole_doc_owner.get(doc, "")
                in_mole_anywhere = bool(mole_owner)
                in_submit = any(d["doc"] == doc for d in submit_docs) if doc else False

                excel_mark = doc if in_excel else ("—" if not excel_docs else "НЕТ")
                if in_mole:
                    mole_mark = doc
                elif in_mole_anywhere:
                    mole_mark = f"OTHER:{mole_owner[-12:]}"
                else:
                    mole_mark = "НЕТ"
                submit_mark = doc if in_submit else ("—" if not submit_docs else "НЕТ")

                if not doc:
                    verdict = "NO_DOC_IN_CRM"
                elif in_excel and (in_mole or in_mole_anywhere):
                    verdict = "OK excel+1c"
                elif in_excel and not in_mole_anywhere:
                    verdict = "excel OK, 1C API НЕТ номера"
                elif not in_excel and in_mole_anywhere:
                    verdict = "в 1C есть, в excel НЕТ"
                else:
                    verdict = "check"

                print(
                    f"{row['line_no']:>2} {doc or '—':<16} {excel_mark:<16} "
                    f"{mole_mark:<16} {submit_mark:<16} {verdict}"
                )

            # Mole docs on this order not in CRM
            crm_set = {r["doc"] for r in crm_docs if r["doc"]}
            mole_set = {d["doc"] for d in mole_docs}
            only_mole = sorted(mole_set - crm_set)
            if only_mole:
                print(f"\nMole filter has extra docs not in CRM: {only_mole}")

            # Excel docs matched to this order's amounts that are missing in mole
            print("\n-- where are CRM docs in Mole filter (any order)? --")
            for row in crm_docs:
                doc = row["doc"]
                if not doc:
                    continue
                owner = mole_doc_owner.get(doc)
                print(f"  {doc} -> {owner or 'NOT FOUND IN FILTER РЕЕСТР'}")

    # Search specific interesting docs from excel РС block for #16
    interesting = [
        "РС-000530001",
        "РС-000616001",
        "РС-000623004",
        "ЛР-000401001",
        "АФ-000417002",
    ]
    print("\n======== sample doc search in Mole filter ========")
    for d in interesting:
        dd = _norm_doc(d)
        print(f"  {dd} -> {mole_doc_owner.get(dd, 'NOT FOUND')}")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
