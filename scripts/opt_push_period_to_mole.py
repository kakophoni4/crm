#!/usr/bin/env python3
"""Push CRM OPT orders to Mole/1C WITHOUT touching the running API config.

Use a one-shot docker exec with demo URL override — staging workers keep
the production MOLE_API_BASE_URL.

  # dry-run (list only)
  docker exec -e PYTHONUNBUFFERED=1 \\
    -e MOLE_API_BASE_URL=http://45.142.193.159/DEMO_BASE \\
    -e MOLE_API_USERNAME=... -e MOLE_API_PASSWORD=... \\
    crm-staging-api python scripts/opt_push_period_to_mole.py --period 2/26 --dry-run

  # create/overwrite 4 times (no delete_extra)
  docker exec -e PYTHONUNBUFFERED=1 \\
    -e MOLE_API_BASE_URL=http://45.142.193.159/DEMO_BASE \\
    crm-staging-api python scripts/opt_push_period_to_mole.py --period 2/26 --times 4

  # subset
  docker exec -e PYTHONUNBUFFERED=1 \\
    -e MOLE_API_BASE_URL=http://45.142.193.159/DEMO_BASE \\
    crm-staging-api python scripts/opt_push_period_to_mole.py --period 2/26 --limit 10 --times 4
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Fresh settings for THIS process (env override). Clear cache if imported early.
from app.shared import settings as settings_mod  # noqa: E402

settings_mod.get_settings.cache_clear()
settings_mod.settings = settings_mod.get_settings()

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import selectinload  # noqa: E402

from app.modules.db.models.lead_opt_order import LeadOptOrder  # noqa: E402
from app.modules.leads.opt.mole_client import (  # noqa: E402
    MoleApiError,
    get_order,
    post_opt_order,
    put_order,
)
from app.modules.leads.opt.periods import normalize_period_code  # noqa: E402
from app.modules.leads.opt.service import OptOrderService  # noqa: E402
from app.shared.db import get_session_factory  # noqa: E402
from app.shared.settings import get_settings  # noqa: E402


def _log(msg: str) -> None:
    print(msg, flush=True)


async def _push_one(service: OptOrderService, order: LeadOptOrder) -> str:
    await service._ensure_order_requisites(order)
    payload = service._build_mole_payload(order)
    try:
        await put_order(order.crm_id, payload)
        return "put"
    except MoleApiError:
        await post_opt_order(payload)
        return "post"


async def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--period", default="2/26")
    p.add_argument("--times", type=int, default=1, help="How many full push passes")
    p.add_argument("--limit", type=int, default=0, help="Max orders (0=all)")
    p.add_argument("--order-ids", default="", help="Comma-separated lead_opt_orders.id")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    period = normalize_period_code(args.period)
    if period is None:
        _log(f"Bad period: {args.period!r}")
        return 1

    cfg = get_settings()
    _log(f"Target Mole URL: {cfg.mole_api_base_url!r} path={cfg.mole_api_orders_path!r}")
    if not cfg.mole_api_base_url.strip():
        _log("MOLE_API_BASE_URL empty — abort")
        return 1

    sf = get_session_factory()
    async with sf() as session:
        stmt = (
            select(LeadOptOrder)
            .where(
                LeadOptOrder.deleted_at.is_(None),
                LeadOptOrder.status == "submitted",
                LeadOptOrder.period_code == period,
                LeadOptOrder.crm_id.is_not(None),
            )
            .options(selectinload(LeadOptOrder.lines))
            .order_by(LeadOptOrder.id.asc())
        )
        if args.order_ids.strip():
            ids = [int(x) for x in args.order_ids.split(",") if x.strip()]
            stmt = stmt.where(LeadOptOrder.id.in_(ids))
        orders = list((await session.execute(stmt)).scalars().unique().all())
        if args.limit and args.limit > 0:
            orders = orders[: args.limit]

        _log(f"Period={period} orders={len(orders)} times={args.times} dry_run={args.dry_run}")
        for o in orders[:15]:
            _log(
                f"  id={o.id} lead={o.lead_id} no={o.order_no} "
                f"vol={o.total_volume} crm={o.crm_id} lines={len(o.lines)}",
            )
        if len(orders) > 15:
            _log(f"  … +{len(orders) - 15} more")

        if args.dry_run:
            _log("Dry-run only — no HTTP")
            return 0

        service = OptOrderService(session)
        for pass_no in range(1, args.times + 1):
            _log(f"\n=== pass {pass_no}/{args.times} ===")
            ok = fail = 0
            for order in orders:
                try:
                    kind = await _push_one(service, order)
                    ok += 1
                    _log(f"  {kind} ok id={order.id} {order.crm_id}")
                except Exception as exc:  # noqa: BLE001
                    fail += 1
                    _log(f"  FAIL id={order.id} {order.crm_id}: {exc}")
            _log(f"pass {pass_no} done ok={ok} fail={fail}")

            # Spot-check first order after each pass
            if orders:
                sample = orders[0]
                try:
                    body = await get_order(sample.crm_id)
                    _log(
                        f"  sample GET {sample.crm_id} "
                        f"sum={body.get('СуммаИтого') or body.get('Сумма')} "
                        f"crm_vol={sample.total_volume}",
                    )
                except Exception as exc:  # noqa: BLE001
                    _log(f"  sample GET fail: {exc}")

    _log("DONE (CRM DB not modified; production API URL unchanged)")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(line_buffering=True)  # type: ignore[attr-defined]
    except Exception:
        pass
    raise SystemExit(asyncio.run(main()))
