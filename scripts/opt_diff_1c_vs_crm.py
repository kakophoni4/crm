#!/usr/bin/env python3
"""Diff OPT orders: Mole/1C vs CRM for a period.

IMPORTANT: do NOT run «Синхронизировать с 1С» until recovery is done —
sync treats CRM as source of truth and will DELETE extras from 1C.

Usage:
  docker exec -e PYTHONUNBUFFERED=1 crm-staging-api \
    python scripts/opt_diff_1c_vs_crm.py --period 2/26

  # also dump Mole rows missing in CRM:
  docker exec ... python scripts/opt_diff_1c_vs_crm.py --period 2/26 --dump /tmp/missing_in_crm.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from sqlalchemy import select, text

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.modules.db.models.lead_opt_order import LeadOptOrder  # noqa: E402
from app.modules.leads.opt.mole_client import filter_orders, mole_session  # noqa: E402
from app.modules.leads.opt.periods import normalize_period_code, period_code_to_mole_iso  # noqa: E402
from app.modules.leads.opt.sync_diff import mole_crm_id, mole_is_deleted  # noqa: E402
from app.shared.db import get_session_factory  # noqa: E402


def _log(msg: str) -> None:
    print(msg, flush=True)


def _buyer_inn(row: dict) -> str:
    buyer = row.get("Покупатель") or row.get("buyer") or {}
    if isinstance(buyer, dict):
        return str(buyer.get("ИНН") or buyer.get("Inn") or buyer.get("inn") or "").strip()
    return ""


def _amount(row: dict) -> float:
    raw = row.get("Сумма") or row.get("amount") or 0
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


async def _crm_ids(period: str) -> dict[str, LeadOptOrder]:
    session_factory = get_session_factory()
    async with session_factory() as session:
        # include soft-deleted so we know if already recoverable locally
        try:
            rows = (
                await session.execute(
                    select(LeadOptOrder).where(LeadOptOrder.period_code == period),
                )
            ).scalars().all()
        except Exception:
            rows = (
                await session.execute(
                    text(
                        "SELECT id, lead_id, crm_id, status, buyer_inn, "
                        "total_volume, commission_due FROM lead_opt_orders "
                        "WHERE period_code = :p"
                    ),
                    {"p": period},
                )
            ).mappings().all()
            return {str(r["crm_id"]): r for r in rows if r.get("crm_id")}  # type: ignore[return-value]
        return {str(o.crm_id): o for o in rows if o.crm_id}


async def _amain(period_raw: str, dump: str | None) -> int:
    period = normalize_period_code(period_raw)
    if period is None:
        _log(f"Bad period: {period_raw!r}")
        return 1
    iso = period_code_to_mole_iso(period)
    if iso is None:
        _log("Cannot map period to ISO")
        return 1

    _log(f"Period {period} → Mole Период={iso}")
    _log("Fetching 1C filter…")
    async with mole_session():
        remote_rows = await filter_orders(period_iso=iso)
    _log(f"1C rows: {len(remote_rows)}")

    remote_by_id: dict[str, dict] = {}
    remote_deleted = 0
    for row in remote_rows:
        cid = mole_crm_id(row)
        if not cid:
            continue
        if mole_is_deleted(row):
            remote_deleted += 1
            continue
        remote_by_id[cid] = row

    _log(f"1C active (Удален!=true): {len(remote_by_id)}  marked_deleted_in_1c: {remote_deleted}")

    crm = await _crm_ids(period)
    crm_active = {}
    crm_soft = {}
    for cid, o in crm.items():
        deleted = getattr(o, "deleted_at", None)
        if deleted is not None:
            crm_soft[cid] = o
        else:
            crm_active[cid] = o

    _log(f"CRM period={period}: active={len(crm_active)} soft_deleted={len(crm_soft)}")

    only_1c = sorted(set(remote_by_id) - set(crm_active) - set(crm_soft))
    only_crm = sorted(set(crm_active) - set(remote_by_id))
    soft_still_in_1c = sorted(set(crm_soft) & set(remote_by_id))

    _log("")
    _log("=== IN 1C, MISSING IN CRM (recovery candidates) ===")
    _log(f"count: {len(only_1c)}")
    missing_payloads = []
    for cid in only_1c:
        row = remote_by_id[cid]
        buyer = _buyer_inn(row)
        amt = _amount(row)
        comment = str(row.get("Комментарий") or row.get("comment") or "")[:80]
        _log(f"  CRMid={cid} buyer_inn={buyer} sum≈{amt:,.2f} comment={comment!r}")
        missing_payloads.append(row)

    _log("")
    _log("=== Soft-deleted in CRM but still in 1C (easy restore) ===")
    _log(f"count: {len(soft_still_in_1c)}")
    for cid in soft_still_in_1c:
        o = crm_soft[cid]
        _log(
            f"  CRMid={cid} order_id={getattr(o,'id', '?')} "
            f"lead_id={getattr(o,'lead_id','?')} → "
            f"python scripts/opt_deleted_orders.py --restore {getattr(o,'id','?')}",
        )

    _log("")
    _log("=== IN CRM, NOT IN 1C (would be restored TO 1C by sync) ===")
    _log(f"count: {len(only_crm)}")
    for cid in only_crm[:30]:
        o = crm_active[cid]
        _log(
            f"  CRMid={cid} order_id={getattr(o,'id','?')} "
            f"lead={getattr(o,'lead_id','?')} status={getattr(o,'status','?')}",
        )
    if len(only_crm) > 30:
        _log(f"  … +{len(only_crm)-30} more")

    if dump:
        path = Path(dump)
        path.write_text(
            json.dumps(missing_payloads, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        _log(f"\nDumped {len(missing_payloads)} missing Mole rows → {path}")

    _log("")
    _log("STOP: do not run UI «Синхронизировать с 1С» until these are restored,")
    _log("otherwise sync will DELETE the 1C-only rows as delete_extra.")
    return 0


def main() -> None:
    try:
        sys.stdout.reconfigure(line_buffering=True)  # type: ignore[attr-defined]
    except Exception:
        pass
    p = argparse.ArgumentParser()
    p.add_argument("--period", required=True, help="e.g. 2/26")
    p.add_argument("--dump", default=None, help="JSON path for 1C-only rows")
    args = p.parse_args()
    raise SystemExit(asyncio.run(_amain(args.period, args.dump)))


if __name__ == "__main__":
    main()
