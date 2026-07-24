#!/usr/bin/env python3
"""Dump / restore OPT orders that exist in Mole but not in CRM.

Uses GET /orders/{CRMid}. Prefer restoring soft-deleted rows; otherwise recreate
on a lead matched by buyer INN (or --lead-id).

Usage:
  # dump full Mole payloads for ONLY MOLE list
  docker cp /tmp/mole_extras.json crm-staging-api:/tmp/mole_extras.json
  docker exec -e PYTHONUNBUFFERED=1 crm-staging-api \\
    python scripts/opt_restore_from_mole.py --json /tmp/mole_extras.json --dump

  # restore (creates submitted orders; does NOT call sync-1c)
  docker exec -e PYTHONUNBUFFERED=1 crm-staging-api \\
    python scripts/opt_restore_from_mole.py --json /tmp/mole_extras.json --apply

  # force lead for all
  ... --apply --lead-id 323
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select, text

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.modules.db.models.lead_opt_order import LeadOptOrder  # noqa: E402
from app.modules.leads.opt.mole_client import get_order  # noqa: E402
from app.modules.leads.opt.repository import OptOrderRepository  # noqa: E402
from app.modules.leads.opt.sync_diff import mole_crm_id, mole_is_deleted  # noqa: E402
from app.modules.leads.opt.vat import split_vat_included  # noqa: E402
from app.shared.db import get_session_factory  # noqa: E402


def _log(msg: str) -> None:
    print(msg, flush=True)


def _party(obj: object) -> tuple[str, str | None, str | None]:
    if not isinstance(obj, dict):
        return "", None, None
    inn = str(obj.get("ИНН") or obj.get("INN") or "").strip()
    kpp = obj.get("КПП") or obj.get("KPP")
    name = obj.get("Наименование") or obj.get("Name")
    kpp_s = str(kpp).strip() if kpp is not None and str(kpp).strip() else None
    name_s = str(name).strip() if name is not None and str(name).strip() else None
    return inn, kpp_s, name_s


def _parse_date(raw: object) -> date | None:
    if raw is None:
        return None
    if isinstance(raw, date) and not isinstance(raw, datetime):
        return raw
    text = str(raw).strip()[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _registry_lines(body: dict[str, Any], *, vat_rate: Decimal) -> list[dict[str, object]]:
    registry = body.get("Реестр") or body.get("Registry") or []
    if not isinstance(registry, list):
        return []
    lines: list[dict[str, object]] = []
    for row in registry:
        if not isinstance(row, dict):
            continue
        line_crm = mole_crm_id(row) or ""
        supplier = row.get("Поставщик") or row.get("Supplier")
        sinn, skpp, sname = _party(supplier)
        doc_date = _parse_date(row.get("ДатаДокумента") or row.get("DocumentDate"))
        try:
            amount = Decimal(str(row.get("Сумма") if "Сумма" in row else row.get("Amount") or 0))
        except Exception:
            amount = Decimal("0")
        if not line_crm or not sinn or doc_date is None or amount <= 0:
            continue
        vat_raw = row.get("СуммаНДС") if "СуммаНДС" in row else row.get("VatAmount")
        wo_raw = row.get("СуммаБезНДС") if "СуммаБезНДС" in row else row.get("AmountWithoutVat")
        if vat_raw is not None and wo_raw is not None:
            vat_amount = Decimal(str(vat_raw))
            amount_without_vat = Decimal(str(wo_raw))
        else:
            _total, vat_amount, amount_without_vat = split_vat_included(
                amount,
                rate_percent=vat_rate,
            )
        lines.append(
            {
                "crm_id": line_crm,
                "supplier_inn": sinn,
                "supplier_kpp": skpp,
                "supplier_name": sname,
                "document_date": doc_date,
                "amount": float(amount),
                "vat_amount": float(vat_amount),
                "amount_without_vat": float(amount_without_vat),
            },
        )
    return lines


async def _admin_user_id() -> int:
    session_factory = get_session_factory()
    async with session_factory() as session:
        row = (
            await session.execute(
                text(
                    """
                    SELECT id FROM users
                    WHERE role::text IN ('admin', 'chief_accountant')
                    ORDER BY id ASC LIMIT 1
                    """
                ),
            )
        ).first()
        if row is None:
            raise SystemExit("No admin user found")
        return int(row[0])


async def _find_soft_deleted(crm_id: str) -> LeadOptOrder | None:
    session_factory = get_session_factory()
    async with session_factory() as session:
        return (
            await session.execute(
                select(LeadOptOrder).where(
                    LeadOptOrder.crm_id == crm_id,
                    LeadOptOrder.deleted_at.is_not(None),
                ),
            )
        ).scalar_one_or_none()


async def _suggest_lead(buyer_inn: str) -> int | None:
    """Prefer open lead that already has (or had) this buyer_inn."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        row = (
            await session.execute(
                text(
                    """
                    SELECT o.lead_id, count(*) AS cnt,
                           bool_or(l.closed_at IS NULL) AS any_open
                    FROM lead_opt_orders o
                    JOIN leads l ON l.id = o.lead_id
                    WHERE o.buyer_inn = :inn
                    GROUP BY o.lead_id
                    ORDER BY
                      bool_or(l.closed_at IS NULL) DESC,
                      count(*) DESC,
                      o.lead_id DESC
                    LIMIT 1
                    """
                ),
                {"inn": buyer_inn},
            )
        ).first()
        if row:
            return int(row[0])
        return None


async def _dump_one(crm_id: str) -> dict[str, Any]:
    body = await get_order(crm_id)
    buyer_inn, buyer_kpp, buyer_name = _party(body.get("Покупатель") or body.get("Buyer"))
    registry_raw = body.get("Реестр") or body.get("Registry") or body.get("реестр")
    reg_len = len(registry_raw) if isinstance(registry_raw, list) else -1
    lines = _registry_lines(body, vat_rate=Decimal("22"))
    volume = sum(Decimal(str(x["amount"])) for x in lines)
    soft = await _find_soft_deleted(crm_id)
    suggest = await _suggest_lead(buyer_inn) if buyer_inn else None
    top_keys = sorted(str(k) for k in body.keys()) if isinstance(body, dict) else []
    info = {
        "crm_id": crm_id,
        "deleted_flag": mole_is_deleted(body),
        "buyer_inn": buyer_inn,
        "buyer_name": buyer_name,
        "mole_keys": top_keys,
        "registry_raw_len": reg_len,
        "lines": len(lines),
        "volume": float(volume),
        "soft_deleted_order_id": soft.id if soft else None,
        "soft_deleted_lead_id": soft.lead_id if soft else None,
        "suggested_lead_id": suggest,
        "line_preview": [
            {
                "supplier": x["supplier_inn"],
                "date": str(x["document_date"]),
                "amount": x["amount"],
            }
            for x in lines[:5]
        ],
        "registry_sample": (registry_raw[:1] if isinstance(registry_raw, list) else registry_raw),
    }
    _log(
        f"{crm_id} buyer={buyer_inn} {buyer_name!r} "
        f"registry_raw={reg_len} parsed_lines={len(lines)} volume={volume} "
        f"soft={info['soft_deleted_order_id']} suggest_lead={suggest} "
        f"keys={top_keys}",
    )
    if reg_len == 0 or reg_len == -1:
        _log(f"    EMPTY REGISTRY sample={info['registry_sample']!r}")
    for p in info["line_preview"]:
        _log(f"    {p}")
    # also write per-order json for inspection
    out = Path(f"/tmp/mole_order_{crm_id}.json")
    out.write_text(json.dumps(body, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    _log(f"    wrote {out}")
    return info


async def _apply_one(
    crm_id: str,
    *,
    lead_id_override: int | None,
    actor_id: int,
    period_code: str,
    dry_run: bool,
) -> str:
    existing_active = None
    session_factory = get_session_factory()
    async with session_factory() as session:
        existing_active = (
            await session.execute(
                select(LeadOptOrder).where(
                    LeadOptOrder.crm_id == crm_id,
                    LeadOptOrder.deleted_at.is_(None),
                ),
            )
        ).scalar_one_or_none()
    if existing_active is not None:
        return f"SKIP already active id={existing_active.id} lead={existing_active.lead_id}"

    soft = await _find_soft_deleted(crm_id)
    if soft is not None:
        if dry_run:
            return f"DRY restore soft id={soft.id} lead={soft.lead_id}"
        async with session_factory() as session:
            order = (
                await session.execute(select(LeadOptOrder).where(LeadOptOrder.id == soft.id))
            ).scalar_one()
            order.deleted_at = None
            order.deleted_by = None
            await session.commit()
        return f"RESTORED soft id={soft.id} lead={soft.lead_id}"

    body = await get_order(crm_id)
    if mole_is_deleted(body):
        return f"SKIP mole Удален=true {crm_id}"

    buyer_inn, buyer_kpp, buyer_name = _party(body.get("Покупатель") or body.get("Buyer"))
    lines = _registry_lines(body, vat_rate=Decimal("22"))
    if not buyer_inn or not lines:
        return f"SKIP empty buyer/lines {crm_id} buyer={buyer_inn} lines={len(lines)}"

    lead_id = lead_id_override or await _suggest_lead(buyer_inn)
    if lead_id is None:
        return f"SKIP no lead for buyer={buyer_inn} {crm_id} (pass --lead-id)"

    if dry_run:
        vol = sum(Decimal(str(x["amount"])) for x in lines)
        return f"DRY create lead={lead_id} buyer={buyer_inn} lines={len(lines)} volume={vol}"

    async with session_factory() as session:
        repo = OptOrderRepository(session)
        # ensure lead exists
        lead_ok = (
            await session.execute(text("SELECT id FROM leads WHERE id=:id"), {"id": lead_id})
        ).first()
        if lead_ok is None:
            return f"FAIL lead {lead_id} not found"

        order = await repo.create_order(
            lead_id=lead_id,
            crm_id=crm_id,
            buyer_inn=buyer_inn,
            buyer_kpp=buyer_kpp,
            buyer_name=buyer_name,
            source_filename=f"restored-from-1c:{crm_id}",
            created_by=actor_id,
            lines=lines,
            period_code=period_code,
            vat_rate_percent=22.0,
        )
        await repo.mark_submitted(
            order,
            actor_id=actor_id,
            request_payload={"restored_from": "mole", "crm_id": crm_id},
            response_payload=body if isinstance(body, dict) else {"raw": str(body)},
            line_numbers={},
        )
        # keep original line document numbers if present
        for item in body.get("Реестр") or []:
            if not isinstance(item, dict):
                continue
            lc = mole_crm_id(item)
            doc = str(item.get("НомерДокумента") or "").strip()
            if not lc or not doc:
                continue
            for line in order.lines:
                if line.crm_id == lc:
                    line.document_number = doc
        await session.commit()
        return f"CREATED id={order.id} lead={lead_id} buyer={buyer_inn} lines={len(lines)}"


async def _amain(args: argparse.Namespace) -> int:
    crm_ids: list[str] = []
    if args.json:
        data = json.loads(Path(args.json).read_text(encoding="utf-8"))
        for item in data.get("only_mole") or []:
            if isinstance(item, dict) and item.get("crm_id"):
                crm_ids.append(str(item["crm_id"]))
            elif isinstance(item, str):
                crm_ids.append(item)
    if args.crm_id:
        crm_ids.extend(args.crm_id)
    crm_ids = list(dict.fromkeys(crm_ids))
    if not crm_ids:
        _log("No crm_ids — pass --json or --crm-id")
        return 1

    _log(f"Targets: {len(crm_ids)}")
    if args.dump or not args.apply:
        for cid in crm_ids:
            try:
                await _dump_one(cid)
            except Exception as exc:  # noqa: BLE001
                _log(f"{cid} DUMP FAIL: {exc}")
        if not args.apply:
            _log("\nDump only. Re-run with --apply to restore/create.")
            return 0

    actor_id = await _admin_user_id()
    _log(f"Applying as user_id={actor_id} period={args.period}")
    for cid in crm_ids:
        try:
            msg = await _apply_one(
                cid,
                lead_id_override=args.lead_id,
                actor_id=actor_id,
                period_code=args.period,
                dry_run=args.dry_run,
            )
            _log(msg)
        except Exception as exc:  # noqa: BLE001
            _log(f"{cid} APPLY FAIL: {exc}")
    return 0


def main() -> None:
    try:
        sys.stdout.reconfigure(line_buffering=True)  # type: ignore[attr-defined]
    except Exception:
        pass
    p = argparse.ArgumentParser()
    p.add_argument("--json", help="mole_extras.json from compare script")
    p.add_argument("--crm-id", action="append", default=[])
    p.add_argument("--dump", action="store_true", help="GET and print details")
    p.add_argument("--apply", action="store_true", help="Restore/create in CRM")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--lead-id", type=int, default=None, help="Force lead for recreates")
    p.add_argument("--period", default="2/26")
    args = p.parse_args()
    if not args.apply:
        args.dump = True
    raise SystemExit(asyncio.run(_amain(args)))


if __name__ == "__main__":
    main()
