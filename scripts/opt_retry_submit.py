#!/usr/bin/env python3
"""Retry failed/queued OPT order submission to 1C (same order id, no re-upload).

Usage on VPS:
  docker exec crm-staging-api python scripts/opt_retry_submit.py --dry-run 17 19
  docker exec crm-staging-api python scripts/opt_retry_submit.py 19
  docker exec crm-staging-api python scripts/opt_retry_submit.py --today-failed
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import select

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.modules.db.models.lead_opt_order import LeadOptOrder  # noqa: E402
from app.modules.leads.opt.repository import OptOrderRepository  # noqa: E402
from app.modules.leads.opt.service import OptOrderService  # noqa: E402
from app.shared.db import get_session_factory  # noqa: E402

_MSK = ZoneInfo("Europe/Moscow")
_RETRYABLE = frozenset({"failed", "queued", "submitting"})


def _today_msk_bounds() -> tuple[datetime, datetime]:
    now_msk = datetime.now(_MSK)
    start = now_msk.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start.replace(hour=23, minute=59, second=59, microsecond=999999)
    return start.astimezone(UTC), end.astimezone(UTC)


async def _resolve_order_ids(
    repo: OptOrderRepository,
    *,
    order_ids: list[int],
    today_failed: bool,
) -> list[int]:
    if order_ids:
        return order_ids
    if not today_failed:
        return []
    start, end = _today_msk_bounds()
    session = repo._session  # noqa: SLF001
    result = await session.execute(
        select(LeadOptOrder.id)
        .where(
            LeadOptOrder.status == "failed",
            LeadOptOrder.created_at >= start,
            LeadOptOrder.created_at <= end,
        )
        .order_by(LeadOptOrder.id),
    )
    return [int(row) for row in result.scalars()]


async def _print_order(repo: OptOrderRepository, order_id: int) -> None:
    order = await repo.get_order(order_id)
    if order is None:
        print(f"  order {order_id}: NOT FOUND")
        return
    print(
        f"  order {order_id}: lead={order.lead_id} no={order.order_no} "
        f"status={order.status} buyer_inn={order.buyer_inn}",
    )
    if order.submission_error:
        print(f"    error: {order.submission_error}")


async def _run(
    *,
    order_ids: list[int],
    today_failed: bool,
    dry_run: bool,
    via_queue: bool,
) -> int:
    session_factory = get_session_factory()
    async with session_factory() as session:
        repo = OptOrderRepository(session)
        ids = await _resolve_order_ids(repo, order_ids=order_ids, today_failed=today_failed)
        if not ids:
            print("Нет заявок для повтора")
            return 1

        print("Заявки:")
        for order_id in ids:
            await _print_order(repo, order_id)

        if dry_run:
            print("DRY-RUN: отправка не выполнялась")
            return 0

        if via_queue:
            from app.modules.leads.opt.queue import enqueue_opt_submit

            for order_id in ids:
                order = await repo.get_order(order_id)
                if order is None or order.status not in _RETRYABLE:
                    print(f"  skip {order_id}: status={order.status if order else 'missing'}")
                    continue
                await enqueue_opt_submit(order_id)
                print(f"  enqueued {order_id} (worker обработает асинхронно)")
            return 0

        service = OptOrderService(session)
        for order_id in ids:
            order = await repo.get_order(order_id)
            if order is None:
                print(f"  skip {order_id}: not found")
                continue
            if order.status == "submitted":
                print(f"  skip {order_id}: already submitted")
                continue
            if order.status not in _RETRYABLE:
                print(f"  skip {order_id}: status={order.status}")
                continue
            print(f"  submitting {order_id}...")
            await service.submit_order_worker(order_id)
            await session.commit()
            refreshed = await repo.get_order(order_id)
            if refreshed is None:
                continue
            print(f"  -> status={refreshed.status}")
            if refreshed.submission_error:
                print(f"     error: {refreshed.submission_error}")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Retry OPT order submit to 1C")
    parser.add_argument("order_ids", nargs="*", type=int, help="Order ids (lead_opt_orders.id)")
    parser.add_argument("--today-failed", action="store_true", help="All failed orders created today (MSK)")
    parser.add_argument("--dry-run", action="store_true", help="Show orders only")
    parser.add_argument("--via-queue", action="store_true", help="Enqueue for worker instead of sync submit")
    args = parser.parse_args()
    if not args.order_ids and not args.today_failed:
        parser.error("Укажите order_ids или --today-failed")
    return asyncio.run(
        _run(
            order_ids=args.order_ids,
            today_failed=args.today_failed,
            dry_run=args.dry_run,
            via_queue=args.via_queue,
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())
