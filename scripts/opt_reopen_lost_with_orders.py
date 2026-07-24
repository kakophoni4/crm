#!/usr/bin/env python3
"""List / reopen leads closed as «Неуспешная продажа» that still have OPT orders.

Usage:
  docker exec -e PYTHONUNBUFFERED=1 crm-staging-api \\
    python scripts/opt_reopen_lost_with_orders.py --list

  docker exec -e PYTHONUNBUFFERED=1 crm-staging-api \\
    python scripts/opt_reopen_lost_with_orders.py --apply --dry-run

  docker exec -e PYTHONUNBUFFERED=1 crm-staging-api \\
    python scripts/opt_reopen_lost_with_orders.py --apply
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from sqlalchemy import text

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.shared.db import get_session_factory  # noqa: E402


def _log(msg: str) -> None:
    print(msg, flush=True)


_LIST_SQL = """
SELECT l.id AS lead_id,
       l.closed_at,
       s.code AS status_code,
       s.label AS status_label,
       c.full_name,
       c.telegram_username,
       l.chat_id,
       count(o.id) AS orders,
       round(coalesce(sum(o.commission_due),0)::numeric, 2) AS commission,
       round(coalesce(sum(o.total_volume),0)::numeric, 2) AS volume
FROM leads l
JOIN statuses s ON s.id = l.status_id
JOIN contacts c ON c.id = l.contact_id
JOIN lead_opt_orders o ON o.lead_id = l.id AND o.deleted_at IS NULL
WHERE l.closed_at IS NOT NULL
  AND s.code = 'lost'
GROUP BY l.id, l.closed_at, s.code, s.label, c.full_name, c.telegram_username, l.chat_id
ORDER BY l.closed_at DESC, l.id DESC
"""


async def _list() -> list[dict]:
    session_factory = get_session_factory()
    async with session_factory() as session:
        rows = (await session.execute(text(_LIST_SQL))).mappings().all()
    items = [dict(r) for r in rows]
    _log(f"lost+OPT leads: {len(items)}")
    total_orders = 0
    total_comm = 0.0
    for r in items:
        total_orders += int(r["orders"])
        total_comm += float(r["commission"] or 0)
        _log(
            f"  lead={r['lead_id']} closed={r['closed_at']} "
            f"contact={r['full_name']!r} @{r['telegram_username'] or ''} "
            f"orders={r['orders']} commission={r['commission']} volume={r['volume']} "
            f"chat_id={r['chat_id']}",
        )
    _log(f"TOTAL orders={total_orders} commission={total_comm:.2f}")
    return items


async def _apply(*, dry_run: bool) -> int:
    items = await _list()
    if not items:
        return 0
    session_factory = get_session_factory()
    async with session_factory() as session:
        open_status = (
            await session.execute(
                text(
                    """
                    SELECT id FROM statuses
                    WHERE kind::text = 'lead_pipeline' AND code = 'in_progress'
                    LIMIT 1
                    """
                ),
            )
        ).scalar_one_or_none()
        if open_status is None:
            open_status = (
                await session.execute(
                    text(
                        """
                        SELECT id FROM statuses
                        WHERE kind::text = 'lead_pipeline' AND code = 'new'
                        LIMIT 1
                        """
                    ),
                )
            ).scalar_one_or_none()
        if open_status is None:
            _log("ERROR: no in_progress/new pipeline status")
            return 1

        _log(f"Reopen status_id={open_status} dry_run={dry_run}")
        for r in items:
            lead_id = int(r["lead_id"])
            chat_id = r["chat_id"]
            if dry_run:
                _log(f"  DRY reopen lead={lead_id} chat={chat_id}")
                continue
            await session.execute(
                text(
                    """
                    UPDATE leads
                    SET closed_at = NULL,
                        retention_expires_at = NULL,
                        status_id = :sid,
                        updated_at = now()
                    WHERE id = :lid
                    """
                ),
                {"sid": int(open_status), "lid": lead_id},
            )
            if chat_id is not None:
                # Restore current lead on chat if empty / pointing elsewhere closed.
                await session.execute(
                    text(
                        """
                        UPDATE chats
                        SET current_lead_id = :lid
                        WHERE id = :cid
                          AND (current_lead_id IS NULL OR current_lead_id = :lid
                               OR NOT EXISTS (
                                 SELECT 1 FROM leads x
                                 WHERE x.id = chats.current_lead_id
                                   AND x.closed_at IS NULL
                               ))
                        """
                    ),
                    {"lid": lead_id, "cid": int(chat_id)},
                )
            _log(f"  REOPENED lead={lead_id}")
        if not dry_run:
            await session.commit()
    return 0


async def _amain(args: argparse.Namespace) -> int:
    if args.apply:
        return await _apply(dry_run=args.dry_run)
    await _list()
    return 0


def main() -> None:
    try:
        sys.stdout.reconfigure(line_buffering=True)  # type: ignore[attr-defined]
    except Exception:
        pass
    p = argparse.ArgumentParser()
    p.add_argument("--list", action="store_true")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    if not args.apply:
        args.list = True
    raise SystemExit(asyncio.run(_amain(args)))


if __name__ == "__main__":
    main()
