#!/usr/bin/env python3
"""Find soft-deleted OPT orders and optionally restore.

Usage on VPS:
  docker exec crm-staging-api python scripts/opt_deleted_orders.py --list
  docker exec crm-staging-api python scripts/opt_deleted_orders.py --list --lead-id 123
  docker exec crm-staging-api python scripts/opt_deleted_orders.py --restore 456
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from sqlalchemy import select, text

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.modules.db.models.lead_opt_order import LeadOptOrder  # noqa: E402
from app.shared.db import get_session_factory  # noqa: E402


def _log(msg: str) -> None:
    print(msg, flush=True)


async def _list(*, lead_id: int | None, limit: int) -> int:
    session_factory = get_session_factory()
    async with session_factory() as session:
        # Column may not exist before migration — fail clearly.
        try:
            await session.execute(text("SELECT deleted_at FROM lead_opt_orders LIMIT 0"))
        except Exception:
            _log("ERROR: column deleted_at missing — run alembic upgrade head first")
            return 1

        stmt = (
            select(LeadOptOrder)
            .where(LeadOptOrder.deleted_at.is_not(None))
            .order_by(LeadOptOrder.deleted_at.desc())
            .limit(limit)
        )
        if lead_id is not None:
            stmt = stmt.where(LeadOptOrder.lead_id == lead_id)
        rows = list((await session.execute(stmt)).scalars().all())

    _log(f"soft_deleted: {len(rows)}")
    for o in rows:
        snap = o.delete_snapshot or {}
        _log(
            f"  id={o.id} lead={o.lead_id} no={o.order_no} status={o.status} "
            f"buyer={o.buyer_inn} volume={o.total_volume} commission={o.commission_due} "
            f"deleted_at={o.deleted_at} deleted_by={o.deleted_by} "
            f"file={o.source_filename!r} snap_lines={len(snap.get('lines') or [])}",
        )
    return 0


async def _restore(order_id: int) -> int:
    session_factory = get_session_factory()
    async with session_factory() as session:
        order = (
            await session.execute(select(LeadOptOrder).where(LeadOptOrder.id == order_id))
        ).scalar_one_or_none()
        if order is None:
            _log(f"NOT FOUND id={order_id}")
            return 1
        if order.deleted_at is None:
            _log(f"NOT DELETED id={order_id} (already active)")
            return 0
        order.deleted_at = None
        order.deleted_by = None
        await session.commit()
        _log(f"RESTORED id={order_id} lead={order.lead_id} order_no={order.order_no}")
    return 0


async def _amain(args: argparse.Namespace) -> int:
    if args.restore is not None:
        return await _restore(args.restore)
    return await _list(lead_id=args.lead_id, limit=args.limit)


def main() -> None:
    p = argparse.ArgumentParser(description="List/restore soft-deleted OPT orders")
    p.add_argument("--list", action="store_true", help="List soft-deleted orders")
    p.add_argument("--lead-id", type=int, default=None)
    p.add_argument("--limit", type=int, default=100)
    p.add_argument("--restore", type=int, default=None, help="Order id to restore")
    args = p.parse_args()
    if not args.list and args.restore is None:
        args.list = True
    raise SystemExit(asyncio.run(_amain(args)))


if __name__ == "__main__":
    main()
