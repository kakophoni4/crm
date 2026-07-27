#!/usr/bin/env python3
"""List CRM OPT orders that Mole filter would treat as restore candidates.

  docker exec -e PYTHONUNBUFFERED=1 crm-staging-api \\
    python scripts/opt_list_restore_candidates.py --period 2/26
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sqlalchemy import text

from app.modules.leads.opt.mole_client import filter_orders
from app.modules.leads.opt.periods import normalize_period_code, period_code_to_mole_iso
from app.modules.leads.opt.sync_diff import mole_crm_id, mole_is_deleted
from app.shared.db import get_session_factory


def _log(msg: str) -> None:
    print(msg, flush=True)


async def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--period", default="2/26")
    args = p.parse_args()
    period = normalize_period_code(args.period)
    if period is None:
        _log(f"Bad period: {args.period!r}")
        return 1
    iso = period_code_to_mole_iso(period)
    if iso is None:
        _log("Cannot map period to Mole ISO")
        return 1

    sf = get_session_factory()
    async with sf() as s:
        crm = (
            await s.execute(
                text(
                    """
                    SELECT id, lead_id, order_no, crm_id, buyer_name,
                           ROUND(total_volume::numeric, 2) AS vol, status
                    FROM lead_opt_orders
                    WHERE deleted_at IS NULL
                      AND period_code = :period
                      AND status = 'submitted'
                      AND crm_id IS NOT NULL
                    ORDER BY id
                    """
                ),
                {"period": period},
            )
        ).mappings().all()

    mole = await filter_orders(period_iso=iso)
    active: dict[str, dict] = {}
    deleted: dict[str, dict] = {}
    for row in mole:
        if not isinstance(row, dict):
            continue
        cid = mole_crm_id(row)
        if not cid:
            continue
        if mole_is_deleted(row):
            deleted[cid] = row
        else:
            active[cid] = row

    only_crm = [r for r in crm if r["crm_id"] not in active]
    _log(f"Period CRM={period} Mole ISO={iso}")
    _log(f"CRM submitted={len(crm)} Mole active={len(active)} deleted_flag={len(deleted)}")
    _log(f"ONLY CRM / restore-candidates: {len(only_crm)}")
    for r in only_crm:
        flag = "IN_FILTER_DELETED" if r["crm_id"] in deleted else "MISSING_IN_FILTER"
        _log(
            f"  id={r['id']} lead={r['lead_id']} no={r['order_no']} "
            f"vol={r['vol']} {flag}",
        )
        _log(f"    {r['crm_id']} | {str(r['buyer_name'])[:70]}")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(line_buffering=True)  # type: ignore[attr-defined]
    except Exception:
        pass
    raise SystemExit(asyncio.run(main()))
