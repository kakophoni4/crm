#!/usr/bin/env python3
"""Find «remainder» OPT uploads that were added because the first file was truncated.

For each truncated order (source Excel available): take lines that the NEW parser
sees but DB does not, then look for other orders on the same lead whose lines
match those missing rows (supplier_inn + date + amount).

Read-only. Does not change DB.

Usage:
  docker exec -e PYTHONUNBUFFERED=1 crm-staging-api \\
    python scripts/opt_find_remainder_orders.py --orders 253,250,249,179,178

  docker exec -e PYTHONUNBUFFERED=1 crm-staging-api \\
    python scripts/opt_find_remainder_orders.py --lead-id 363
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import text

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.modules.leads.opt.parser import parse_application_workbook  # noqa: E402
from app.shared.db import get_session_factory  # noqa: E402
from app.shared.storage import get_file_storage  # noqa: E402


def _log(msg: str) -> None:
    print(msg, flush=True)


def _money(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01')):,.2f}".replace(",", " ")


def _parse_ids(raw: str | None) -> list[int]:
    if not raw:
        return []
    return [int(p.strip()) for p in raw.split(",") if p.strip()]


def _d(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def _line_key(supplier_inn: str, doc_date: date, amount: Decimal) -> tuple[str, date, str]:
    return (str(supplier_inn), doc_date, f"{Decimal(amount).quantize(Decimal('0.01'))}")


async def _fetch_bytes(storage_key: str) -> bytes | None:
    try:
        data, _ct = await get_file_storage().get_bytes(storage_key)
        return data
    except Exception as exc:
        _log(f"  WARN storage: {exc}")
        return None


async def _load_source(
    session: Any,
    *,
    source_message_id: int | None,
    source_attachment_index: int | None,
    source_filename: str | None,
    chat_id: int | None,
) -> bytes | None:
    if source_message_id is not None and source_attachment_index is not None:
        row = (
            await session.execute(
                text(
                    """
                    SELECT att->>'storage_key' AS storage_key
                    FROM messages m
                    CROSS JOIN LATERAL jsonb_array_elements(
                      CASE WHEN jsonb_typeof(m.attachments)='array'
                           THEN m.attachments ELSE '[]'::jsonb END
                    ) WITH ORDINALITY AS t(att, ord)
                    WHERE m.id = :mid AND (t.ord - 1) = :idx
                    LIMIT 1
                    """
                ),
                {"mid": int(source_message_id), "idx": int(source_attachment_index)},
            )
        ).mappings().first()
        if row and row["storage_key"]:
            data = await _fetch_bytes(str(row["storage_key"]))
            if data:
                return data

    fname = (source_filename or "").strip()
    if fname and chat_id is not None:
        row = (
            await session.execute(
                text(
                    """
                    SELECT att->>'storage_key' AS storage_key
                    FROM messages m
                    CROSS JOIN LATERAL jsonb_array_elements(
                      CASE WHEN jsonb_typeof(m.attachments)='array'
                           THEN m.attachments ELSE '[]'::jsonb END
                    ) att
                    WHERE m.chat_id = :cid
                      AND nullif(att->>'storage_key','') IS NOT NULL
                      AND lower(coalesce(att->>'filename', att->>'name', '')) = lower(:fname)
                    ORDER BY m.id DESC
                    LIMIT 1
                    """
                ),
                {"cid": chat_id, "fname": fname},
            )
        ).mappings().first()
        if row and row["storage_key"]:
            data = await _fetch_bytes(str(row["storage_key"]))
            if data:
                return data
    return None


async def _amain(args: argparse.Namespace) -> int:
    session_factory = get_session_factory()
    order_ids = _parse_ids(args.orders)

    async with session_factory() as session:
        params: dict[str, object] = {}
        filters = ["o.deleted_at IS NULL"]
        if order_ids:
            filters.append("o.id = ANY(:ids)")
            params["ids"] = order_ids
        if args.lead_id is not None:
            filters.append("o.lead_id = :lead_id")
            params["lead_id"] = args.lead_id

        truncated_candidates = (
            await session.execute(
                text(
                    f"""
                    SELECT o.id, o.lead_id, o.order_no, o.source_filename,
                           o.source_message_id, o.source_attachment_index,
                           l.chat_id
                    FROM lead_opt_orders o
                    JOIN leads l ON l.id = o.lead_id
                    WHERE {" AND ".join(filters)}
                    ORDER BY o.lead_id, o.order_no
                    """
                ),
                params,
            )
        ).mappings().all()

        # Preload all lines for leads we touch.
        lead_ids = sorted({int(r["lead_id"]) for r in truncated_candidates})
        if not lead_ids:
            _log("no orders to check")
            return 0

        all_orders = (
            await session.execute(
                text(
                    """
                    SELECT o.id, o.lead_id, o.order_no, o.source_filename, o.status,
                           o.created_at, o.total_volume, o.commission_due
                    FROM lead_opt_orders o
                    WHERE o.deleted_at IS NULL
                      AND o.lead_id = ANY(:leads)
                    ORDER BY o.lead_id, o.order_no
                    """
                ),
                {"leads": lead_ids},
            )
        ).mappings().all()

        all_lines = (
            await session.execute(
                text(
                    """
                    SELECT ln.order_id, ln.supplier_inn, ln.document_date, ln.amount
                    FROM lead_opt_order_lines ln
                    JOIN lead_opt_orders o ON o.id = ln.order_id
                    WHERE o.deleted_at IS NULL
                      AND o.lead_id = ANY(:leads)
                    """
                ),
                {"leads": lead_ids},
            )
        ).mappings().all()

    lines_by_order: dict[int, set[tuple[str, date, str]]] = {}
    for ln in all_lines:
        d = _d(ln["document_date"])
        if d is None:
            continue
        oid = int(ln["order_id"])
        lines_by_order.setdefault(oid, set()).add(
            _line_key(str(ln["supplier_inn"]), d, Decimal(str(ln["amount"]))),
        )

    orders_by_lead: dict[int, list[Any]] = {}
    for o in all_orders:
        orders_by_lead.setdefault(int(o["lead_id"]), []).append(o)

    _log(f"checking truncated sources: {len(truncated_candidates)}")
    remainders: list[dict[str, Any]] = []

    async with session_factory() as session:
        for row in truncated_candidates:
            oid = int(row["id"])
            content = await _load_source(
                session,
                source_message_id=(
                    int(row["source_message_id"])
                    if row["source_message_id"] is not None
                    else None
                ),
                source_attachment_index=(
                    int(row["source_attachment_index"])
                    if row["source_attachment_index"] is not None
                    else None
                ),
                source_filename=row["source_filename"],
                chat_id=int(row["chat_id"]) if row["chat_id"] is not None else None,
            )
            if content is None:
                continue
            try:
                parsed = parse_application_workbook(content)
            except Exception:
                continue

            file_keys = {
                _line_key(ln.supplier_inn, ln.document_date, ln.amount) for ln in parsed.lines
            }
            db_keys = lines_by_order.get(oid, set())
            missing = file_keys - db_keys
            if not missing:
                continue

            _log(
                f"\nTRUNCATED order={oid} lead={row['lead_id']} no={row['order_no']} "
                f"file={row['source_filename']!r} missing_lines={len(missing)}",
            )
            for k in sorted(missing, key=lambda x: (x[1], x[2])):
                _log(f"  missing: inn={k[0]} date={k[1]} amount={k[2]}")

            # Find other orders on same lead covering those missing keys.
            best: list[tuple[int, int, Any]] = []  # (overlap, order_id, row)
            for other in orders_by_lead.get(int(row["lead_id"]), []):
                other_id = int(other["id"])
                if other_id == oid:
                    continue
                other_keys = lines_by_order.get(other_id, set())
                overlap = missing & other_keys
                if not overlap:
                    continue
                best.append((len(overlap), other_id, other, overlap))

            best.sort(reverse=True)
            if not best:
                _log("  → remainder not found in other orders on this lead")
                # Heuristic: filename looks like испр/догруз/часть after this one
                fname = (row["source_filename"] or "").lower()
                for other in orders_by_lead.get(int(row["lead_id"]), []):
                    other_id = int(other["id"])
                    if other_id == oid:
                        continue
                    oname = (other["source_filename"] or "").lower()
                    if any(
                        tip in oname
                        for tip in ("испр", "догруз", "остат", "хвост", "часть_2", "часть 2", " part")
                    ) and int(other["order_no"]) > int(row["order_no"]):
                        _log(
                            f"  → name-hint candidate order={other_id} no={other['order_no']} "
                            f"file={other['source_filename']!r}",
                        )
                continue

            for overlap_n, other_id, other, overlap in best:
                ratio = overlap_n / max(1, len(missing))
                flag = "LIKELY_REMAINDER" if ratio >= 0.5 else "partial_overlap"
                _log(
                    f"  → [{flag}] order={other_id} no={other['order_no']} "
                    f"file={other['source_filename']!r} "
                    f"overlap={overlap_n}/{len(missing)} "
                    f"vol={_money(Decimal(str(other['total_volume'] or 0)))} "
                    f"commission={_money(Decimal(str(other['commission_due'] or 0)))}",
                )
                remainders.append(
                    {
                        "truncated_id": oid,
                        "truncated_no": int(row["order_no"]),
                        "truncated_file": row["source_filename"],
                        "remainder_id": other_id,
                        "remainder_no": int(other["order_no"]),
                        "remainder_file": other["source_filename"],
                        "lead_id": int(row["lead_id"]),
                        "overlap": overlap_n,
                        "missing": len(missing),
                        "ratio": ratio,
                        "commission": Decimal(str(other["commission_due"] or 0)),
                    },
                )

    _log("\n========== SUMMARY ==========")
    likely = [r for r in remainders if r["ratio"] >= 0.5]
    _log(f"likely remainder orders: {len(likely)}")
    seen: set[int] = set()
    for r in likely:
        if r["remainder_id"] in seen:
            continue
        seen.add(r["remainder_id"])
        _log(
            f"  lead={r['lead_id']}  remainder_order={r['remainder_id']} "
            f"no={r['remainder_no']} file={r['remainder_file']!r} "
            f"covers truncated no={r['truncated_no']} "
            f"({r['overlap']}/{r['missing']} lines) "
            f"commission={_money(r['commission'])}",
        )
        _log(
            f"    после ремонта заявки №{r['truncated_no']} эту "
            f"«догрузку» №{r['remainder_no']} (id={r['remainder_id']}) "
            f"скорее всего нужно soft-delete, иначе дубль в реестре/1С",
        )

    if not likely:
        _log(
            "Явных догрузок по совпадению строк не найдено. "
            "Возможно догружали вручную другими суммами/датами, "
            "или «часть_N» — это разные куски клиента, а не хвост одной заявки.",
        )
    return 0


def main() -> None:
    try:
        sys.stdout.reconfigure(line_buffering=True)  # type: ignore[attr-defined]
    except Exception:
        pass
    p = argparse.ArgumentParser()
    p.add_argument("--orders", default=None)
    p.add_argument("--lead-id", type=int, default=None)
    args = p.parse_args()
    if not args.orders and args.lead_id is None:
        args.orders = "253,250,249,179,178"
    raise SystemExit(asyncio.run(_amain(args)))


if __name__ == "__main__":
    main()
