#!/usr/bin/env python3
"""Compare CRM OPT orders with Mole/1C for a period — list extras in 1C.

IMPORTANT: do NOT run POST /opt-orders/sync-1c before reviewing extras —
sync treats Mole-only rows as delete_extra and will soft-delete them in 1C.

Usage:
  docker exec -e PYTHONUNBUFFERED=1 crm-staging-api \\
    python scripts/opt_compare_1c_extras.py --period 2/26

  docker exec -e PYTHONUNBUFFERED=1 crm-staging-api \\
    python scripts/opt_compare_1c_extras.py --period 2/26 --json /tmp/mole_extras.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from sqlalchemy import or_, select, text

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.modules.db.models.lead_opt_order import LeadOptOrder  # noqa: E402
from app.modules.leads.opt.mole_client import filter_orders, mole_session  # noqa: E402
from app.modules.leads.opt.periods import (  # noqa: E402
    normalize_period_code,
    period_code_to_mole_iso,
)
from app.modules.leads.opt.sync_diff import mole_crm_id, mole_is_deleted  # noqa: E402
from app.shared.db import get_session_factory  # noqa: E402


def _log(msg: str) -> None:
    print(msg, flush=True)


def _buyer_inn(row: dict) -> str:
    party = row.get("Покупатель") or row.get("Buyer") or {}
    if isinstance(party, dict):
        return str(party.get("ИНН") or party.get("INN") or "").strip()
    return ""


def _buyer_name(row: dict) -> str:
    party = row.get("Покупатель") or row.get("Buyer") or {}
    if isinstance(party, dict):
        return str(party.get("Наименование") or party.get("Name") or "").strip()[:80]
    return ""


def _volume(row: dict) -> float:
    registry = row.get("Реестр") or row.get("Registry") or []
    total = 0.0
    if isinstance(registry, list):
        for line in registry:
            if not isinstance(line, dict):
                continue
            raw = line.get("Сумма") or line.get("Amount") or 0
            try:
                total += float(raw)
            except (TypeError, ValueError):
                pass
    return total


async def _crm_ids(period: str) -> set[str]:
    session_factory = get_session_factory()
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(LeadOptOrder.crm_id).where(
                    LeadOptOrder.period_code == period,
                    LeadOptOrder.deleted_at.is_(None),
                    LeadOptOrder.crm_id.is_not(None),
                ),
            )
        ).scalars().all()
        return {str(x).strip() for x in rows if x}


async def _search_people(needles: list[str]) -> None:
    session_factory = get_session_factory()
    async with session_factory() as session:
        for needle in needles:
            _log(f"\n--- search {needle!r} ---")
            q = await session.execute(
                text(
                    """
                    SELECT u.id, u.full_name, u.username, u.role
                    FROM users u
                    WHERE u.full_name ILIKE :n OR u.username ILIKE :n
                    LIMIT 20
                    """
                ),
                {"n": f"%{needle}%"},
            )
            users = q.all()
            if users:
                _log("users:")
                for r in users:
                    _log(f"  id={r[0]} name={r[1]!r} username={r[2]!r} role={r[3]}")
            else:
                _log("users: (none)")

            q2 = await session.execute(
                text(
                    """
                    SELECT c.id, c.full_name, c.telegram_username, c.telegram_user_id
                    FROM contacts c
                    WHERE c.full_name ILIKE :n
                       OR c.telegram_username ILIKE :n
                    LIMIT 20
                    """
                ),
                {"n": f"%{needle}%"},
            )
            contacts = q2.all()
            if contacts:
                _log("contacts:")
                for r in contacts:
                    _log(
                        f"  id={r[0]} name={r[1]!r} tg=@{r[2] or ''} tg_id={r[3]}",
                    )
            else:
                _log("contacts: (none)")

            if contacts:
                cids = [int(r[0]) for r in contacts]
                q3 = await session.execute(
                    text(
                        """
                        SELECT l.id, l.created_at::date, left(coalesce(l.title,''),50),
                               (SELECT count(*) FROM lead_opt_orders o
                                  WHERE o.lead_id=l.id AND o.deleted_at IS NULL) AS orders
                        FROM leads l
                        WHERE l.contact_id = ANY(:cids)
                        ORDER BY l.id DESC
                        LIMIT 40
                        """
                    ),
                    {"cids": cids},
                )
                _log("leads for those contacts:")
                for r in q3.all():
                    _log(f"  lead={r[0]} date={r[1]} orders={r[3]} title={r[2]!r}")


async def _amain(period_raw: str, json_path: str | None, people: list[str]) -> int:
    if people:
        await _search_people(people)

    period = normalize_period_code(period_raw)
    if period is None:
        _log(f"Bad period: {period_raw!r}")
        return 1
    iso = period_code_to_mole_iso(period)
    if iso is None:
        _log("Cannot map period to Mole ISO")
        return 1

    _log("")
    _log("!!! DO NOT run sync-1c until extras are reviewed — it deletes Mole-only rows !!!")
    _log(f"Period CRM={period} Mole ISO={iso}")

    crm_ids = await _crm_ids(period)
    _log(f"CRM active orders in period: {len(crm_ids)}")

    async with mole_session() as session:
        mole_rows = await filter_orders({"Период": iso}, session=session)

    if not isinstance(mole_rows, list):
        _log(f"Unexpected Mole response type: {type(mole_rows)}")
        return 1

    mole_active: dict[str, dict] = {}
    mole_deleted_flag = 0
    for row in mole_rows:
        if not isinstance(row, dict):
            continue
        cid = mole_crm_id(row)
        if not cid:
            continue
        if mole_is_deleted(row):
            mole_deleted_flag += 1
            continue
        mole_active[cid] = row

    _log(f"Mole rows (period filter): {len(mole_rows)}")
    _log(f"Mole active (Удален!=true): {len(mole_active)}")
    _log(f"Mole marked Удален: {mole_deleted_flag}")

    only_crm = sorted(crm_ids - set(mole_active))
    only_mole = sorted(set(mole_active) - crm_ids)
    both = sorted(crm_ids & set(mole_active))

    _log("")
    _log(f"=== IN BOTH: {len(both)} ===")
    _log(f"=== ONLY CRM (missing in 1C): {len(only_crm)} ===")
    for cid in only_crm[:50]:
        _log(f"  {cid}")
    if len(only_crm) > 50:
        _log(f"  … +{len(only_crm) - 50} more")

    _log("")
    _log(f"=== ONLY MOLE (candidates deleted from CRM): {len(only_mole)} ===")
    extras: list[dict] = []
    for cid in only_mole:
        row = mole_active[cid]
        item = {
            "crm_id": cid,
            "buyer_inn": _buyer_inn(row),
            "buyer_name": _buyer_name(row),
            "volume": round(_volume(row), 2),
            "comment": str(row.get("Комментарий") or row.get("Comment") or "")[:120],
            "conducted": row.get("Проведен") if "Проведен" in row else row.get("Posted"),
        }
        extras.append(item)
        _log(
            f"  {cid} buyer={item['buyer_inn']} {item['buyer_name']!r} "
            f"volume={item['volume']} conducted={item['conducted']} "
            f"comment={item['comment']!r}",
        )

    if json_path:
        Path(json_path).write_text(
            json.dumps(
                {
                    "period": period,
                    "period_iso": iso,
                    "crm_count": len(crm_ids),
                    "mole_active_count": len(mole_active),
                    "only_crm": only_crm,
                    "only_mole": extras,
                    "both_count": len(both),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        _log(f"\nWrote {json_path}")

    _log("")
    _log("Next: for each ONLY MOLE crm_id we can rebuild CRM order from Mole GET.")
    _log("Until then — do not press «Синхронизировать с 1С».")
    return 0


def main() -> None:
    try:
        sys.stdout.reconfigure(line_buffering=True)  # type: ignore[attr-defined]
    except Exception:
        pass
    p = argparse.ArgumentParser()
    p.add_argument("--period", default="2/26", help="Q/YY e.g. 2/26")
    p.add_argument("--json", default=None, help="Write extras JSON path inside container")
    p.add_argument(
        "--people",
        nargs="*",
        default=[],
        help="Search users/contacts/leads by name/username",
    )
    args = p.parse_args()
    raise SystemExit(
        asyncio.run(_amain(args.period, args.json, args.people)),
    )


if __name__ == "__main__":
    main()
