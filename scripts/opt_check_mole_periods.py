#!/usr/bin/env python3
"""Check Mole Период vs CRM period_code for submitted OPT orders.

  docker cp scripts/opt_check_mole_periods.py crm-staging-api:/app/scripts/

  # period 2/26 only, sample first failures
  docker exec -e PYTHONUNBUFFERED=1 crm-staging-api \\
    python scripts/opt_check_mole_periods.py --period 2/26

  # all periods, limit concurrent GETs
  docker exec -e PYTHONUNBUFFERED=1 crm-staging-api \\
    python scripts/opt_check_mole_periods.py --all --limit 500
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

from app.modules.leads.opt.mole_client import get_order, mole_session
from app.modules.leads.opt.periods import normalize_period_code, period_code_to_mole_iso
from app.shared.db import get_session_factory


def _period_date(raw: object) -> str:
    text_v = str(raw or "").strip()
    if not text_v:
        return ""
    return text_v[:10]


async def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--period", default="2/26", help="CRM period code, e.g. 2/26")
    p.add_argument("--all", action="store_true", help="All submitted orders with period_code")
    p.add_argument("--limit", type=int, default=0, help="Max orders to check (0=all)")
    p.add_argument("--concurrency", type=int, default=8)
    p.add_argument("--show-ok", action="store_true")
    args = p.parse_args()

    period = None if args.all else normalize_period_code(args.period)
    if not args.all and period is None:
        print(f"Bad period: {args.period!r}")
        return 1

    sf = get_session_factory()
    async with sf() as s:
        if args.all:
            rows = (
                await s.execute(
                    text(
                        """
                        SELECT id, lead_id, order_no, crm_id, period_code,
                               left(buyer_name, 40) AS buyer,
                               ROUND(total_volume::numeric, 2) AS vol
                        FROM lead_opt_orders
                        WHERE deleted_at IS NULL
                          AND status = 'submitted'
                          AND crm_id IS NOT NULL
                          AND period_code IS NOT NULL
                        ORDER BY id
                        """
                    ),
                )
            ).mappings().all()
        else:
            rows = (
                await s.execute(
                    text(
                        """
                        SELECT id, lead_id, order_no, crm_id, period_code,
                               left(buyer_name, 40) AS buyer,
                               ROUND(total_volume::numeric, 2) AS vol
                        FROM lead_opt_orders
                        WHERE deleted_at IS NULL
                          AND status = 'submitted'
                          AND crm_id IS NOT NULL
                          AND period_code = :period
                        ORDER BY id
                        """
                    ),
                    {"period": period},
                )
            ).mappings().all()

    if args.limit and args.limit > 0:
        rows = rows[: args.limit]

    print(f"Checking {len(rows)} CRM orders "
          f"({'all periods' if args.all else f'period={period}'})")

    sem = asyncio.Semaphore(max(1, args.concurrency))
    bad_empty = 0
    bad_mismatch = 0
    ok = 0
    get_fail = 0
    deleted = 0

    async def one(r: dict) -> None:
        nonlocal bad_empty, bad_mismatch, ok, get_fail, deleted
        expected = period_code_to_mole_iso(str(r["period_code"]))
        async with sem:
            try:
                body = await get_order(r["crm_id"])
            except Exception as exc:  # noqa: BLE001
                get_fail += 1
                print(
                    f"GET_FAIL id={r['id']} lead={r['lead_id']} no={r['order_no']} "
                    f"crm={r['crm_id']} | {exc}"
                )
                return

        actual = _period_date(body.get("Период"))
        is_del = str(body.get("Удален") or "").lower() in {"true", "1", "yes", "да"}
        if is_del:
            deleted += 1

        if actual in {"", "0001-01-01"}:
            bad_empty += 1
            print(
                f"EMPTY  id={r['id']} lead={r['lead_id']} no={r['order_no']} "
                f"crm_period={r['period_code']} expect={expected} "
                f"mole={actual or '—'} deleted={is_del} | {r['buyer']}"
            )
            return

        if expected and actual != expected:
            bad_mismatch += 1
            print(
                f"MISMATCH id={r['id']} lead={r['lead_id']} no={r['order_no']} "
                f"crm_period={r['period_code']} expect={expected} "
                f"mole={actual} deleted={is_del} | {r['buyer']}"
            )
            return

        ok += 1
        if args.show_ok:
            print(
                f"OK     id={r['id']} lead={r['lead_id']} no={r['order_no']} "
                f"mole={actual}"
            )

    async with mole_session():
        await asyncio.gather(*(one(dict(r)) for r in rows))

    print(
        f"\nDONE ok={ok} empty_or_0001={bad_empty} mismatch={bad_mismatch} "
        f"deleted_flag={deleted} get_fail={get_fail} total={len(rows)}"
    )
    return 0 if bad_empty == 0 and bad_mismatch == 0 and get_fail == 0 else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(line_buffering=True)  # type: ignore[attr-defined]
    except Exception:
        pass
    raise SystemExit(asyncio.run(main()))
