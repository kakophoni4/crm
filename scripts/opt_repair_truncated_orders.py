#!/usr/bin/env python3
"""List / repair OPT orders truncated by the old Excel parser.

Default: list only (no DB writes).
Repair: re-parse source attachment, replace lines, recalc commission, re-queue 1C submit.

Usage on VPS:
  # operators for known suspects from last scan
  docker exec -e PYTHONUNBUFFERED=1 crm-staging-api \\
    python scripts/opt_repair_truncated_orders.py --orders 253,250,249,179,178

  # dry-run repair (shows what would change)
  docker exec -e PYTHONUNBUFFERED=1 crm-staging-api \\
    python scripts/opt_repair_truncated_orders.py --orders 253,250,249,179,178 --repair --dry-run

  # apply repair + re-queue Mole/1C
  docker exec -e PYTHONUNBUFFERED=1 crm-staging-api \\
    python scripts/opt_repair_truncated_orders.py --orders 253,250,249,179,178 --repair
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import text

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.modules.db.models.lead_opt_order import LeadOptOrder, LeadOptOrderLine  # noqa: E402
from app.modules.leads.opt.fingerprint import compute_application_fingerprint  # noqa: E402
from app.modules.leads.opt.parser import parse_application_workbook  # noqa: E402
from app.modules.leads.opt.queue import enqueue_opt_submit  # noqa: E402
from app.modules.leads.opt.repository import OptOrderRepository  # noqa: E402
from app.modules.leads.opt.vat import normalize_opt_vat_rate, split_vat_included  # noqa: E402
from app.shared.db import get_session_factory  # noqa: E402
from app.shared.storage import get_file_storage  # noqa: E402


def _log(msg: str) -> None:
    print(msg, flush=True)


def _money(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01')):,.2f}".replace(",", " ")


def _parse_ids(raw: str) -> list[int]:
    return [int(part.strip()) for part in raw.split(",") if part.strip()]


async def _fetch_bytes(storage_key: str) -> bytes | None:
    try:
        data, _ct = await get_file_storage().get_bytes(storage_key)
        return data
    except Exception as exc:
        _log(f"  WARN storage: {exc}")
        return None


async def _load_source(session: Any, order: LeadOptOrder) -> tuple[bytes | None, str]:
    if order.source_message_id is None or order.source_attachment_index is None:
        return None, "no_source_attachment"
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
            {"mid": int(order.source_message_id), "idx": int(order.source_attachment_index)},
        )
    ).mappings().first()
    if not row or not row["storage_key"]:
        return None, "attachment_missing"
    data = await _fetch_bytes(str(row["storage_key"]))
    if not data:
        return None, "storage_fail"
    return data, "source_attachment"


async def _list_orders(order_ids: list[int]) -> int:
    session_factory = get_session_factory()
    async with session_factory() as session:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT o.id AS order_id,
                           o.lead_id,
                           o.order_no,
                           o.status,
                           o.source_filename,
                           o.total_volume,
                           o.commission_due,
                           o.crm_id,
                           c.full_name AS contact_name,
                           c.telegram_username,
                           l.chat_id,
                           u.id AS operator_id,
                           u.full_name AS operator_name,
                           (SELECT count(*)::int FROM lead_opt_order_lines ln
                             WHERE ln.order_id = o.id) AS db_lines
                    FROM lead_opt_orders o
                    JOIN leads l ON l.id = o.lead_id
                    JOIN contacts c ON c.id = l.contact_id
                    LEFT JOIN contact_group_assignments cga
                      ON cga.contact_id = l.contact_id AND cga.group_id = l.group_id
                    LEFT JOIN users u ON u.id = cga.owner_user_id
                    WHERE o.id = ANY(:ids)
                    ORDER BY o.lead_id, o.order_no
                    """
                ),
                {"ids": order_ids},
            )
        ).mappings().all()

    _log(f"orders: {len(rows)}")
    _log("")
    _log("Сделка | Заявка | order_id | файл | строк | объём | оператор | контакт | chat")
    _log("-" * 120)
    for r in rows:
        op = r["operator_name"] or f"id={r['operator_id']}" if r["operator_id"] else "—"
        tg = f"@{r['telegram_username']}" if r["telegram_username"] else r["contact_name"]
        _log(
            f"lead={r['lead_id']}  no={r['order_no']}  id={r['order_id']}  "
            f"file={r['source_filename']!r}  lines={r['db_lines']}  "
            f"vol={_money(Decimal(str(r['total_volume'] or 0)))}  "
            f"commission={_money(Decimal(str(r['commission_due'] or 0)))}  "
            f"operator={op!r}  contact={tg!r}  chat={r['chat_id']}",
        )
    _log("")
    _log("Текст для операторов:")
    by_op: dict[str, list[str]] = {}
    for r in rows:
        op = r["operator_name"] or "неизвестно"
        by_op.setdefault(op, []).append(
            f"сделка №{r['lead_id']}, заявка №{r['order_no']} ({r['source_filename']})",
        )
    for op, items in by_op.items():
        _log(f"  → {op}:")
        for item in items:
            _log(f"      • {item} — реестр будет пересобран (добавятся пропущенные строки СФ)")
    return 0


async def _repair(order_ids: list[int], *, dry_run: bool) -> int:
    """Append only missing Excel lines — keep existing line crm_id / document_number."""
    session_factory = get_session_factory()
    repaired = 0
    async with session_factory() as session:
        repo = OptOrderRepository(session)
        for oid in order_ids:
            order = await repo.get_order(oid)
            if order is None or order.deleted_at is not None:
                _log(f"order={oid}: not found / deleted — skip")
                continue
            content, how = await _load_source(session, order)
            if content is None:
                _log(f"order={oid}: cannot repair ({how})")
                continue
            try:
                parsed = parse_application_workbook(content)
            except Exception as exc:
                _log(f"order={oid}: parse fail: {exc}")
                continue

            def _key(inn: str, d: object, amount: object) -> tuple[str, str, str]:
                from datetime import date as date_cls
                from datetime import datetime as datetime_cls

                if isinstance(d, datetime_cls):
                    ds = d.date().isoformat()
                elif isinstance(d, date_cls):
                    ds = d.isoformat()
                else:
                    ds = str(d)
                return (str(inn), ds, f"{Decimal(str(amount)).quantize(Decimal('0.01'))}")

            existing_keys = {
                _key(ln.supplier_inn, ln.document_date, ln.amount) for ln in order.lines
            }
            missing = [
                pl
                for pl in parsed.lines
                if _key(pl.supplier_inn, pl.document_date, pl.amount) not in existing_keys
            ]
            old_n = len(order.lines)
            old_vol = Decimal(str(order.total_volume or 0))
            if not missing:
                _log(f"order={oid}: already complete ({old_n} lines) — skip")
                continue

            add_vol = sum((pl.amount for pl in missing), Decimal("0"))
            _log(
                f"order={oid} lead={order.lead_id} no={order.order_no}: "
                f"keep {old_n} lines, append {len(missing)} "
                f"(+{_money(add_vol)}), via={how} dry_run={dry_run}",
            )
            if dry_run:
                continue

            vat_rate = normalize_opt_vat_rate(order.vat_rate_percent)
            period_code = order.period_code
            next_no = max((ln.line_no for ln in order.lines), default=0) + 1
            for parsed_line in missing:
                unit = None
                if period_code:
                    unit = await repo.get_unit_by_inn_for_period(
                        parsed_line.supplier_inn,
                        period_code,
                    )
                if unit is None:
                    unit = await repo.get_unit_by_inn(parsed_line.supplier_inn)
                total, vat, wo_vat = split_vat_included(parsed_line.amount, rate_percent=vat_rate)
                session.add(
                    LeadOptOrderLine(
                        order_id=order.id,
                        crm_id=repo.new_crm_id("crm-line"),
                        line_no=next_no,
                        supplier_inn=parsed_line.supplier_inn,
                        supplier_kpp=unit.kpp if unit else None,
                        supplier_name=unit.name if unit else None,
                        document_date=parsed_line.document_date,
                        amount=float(total),
                        vat_amount=float(vat),
                        amount_without_vat=float(wo_vat),
                    ),
                )
                next_no += 1

            await session.flush()
            await session.refresh(order, attribute_names=["lines"])
            await repo.apply_pricing_snapshot(order)
            order.content_fingerprint = compute_application_fingerprint(parsed)
            # Re-submit same order.crm_id so 1C updates registry; existing line CRMids stay.
            order.status = "queued"
            order.submission_error = None
            await session.commit()
            await enqueue_opt_submit(order.id)
            repaired += 1
            _log(
                f"  APPENDED order={oid} now_lines={len(order.lines)} "
                f"commission_due={_money(Decimal(str(order.commission_due or 0)))} "
                f"queued for 1C",
            )

    _log(f"repaired={repaired} dry_run={dry_run}")
    return 0


async def _amain(args: argparse.Namespace) -> int:
    ids = _parse_ids(args.orders)
    if not ids:
        _log("ERROR: pass --orders 253,250,...")
        return 1
    await _list_orders(ids)
    if args.repair:
        return await _repair(ids, dry_run=args.dry_run)
    _log("Список выше. Чтобы пересобрать строки/реестр/1С: добавьте --repair [--dry-run]")
    return 0


def main() -> None:
    try:
        sys.stdout.reconfigure(line_buffering=True)  # type: ignore[attr-defined]
    except Exception:
        pass
    p = argparse.ArgumentParser()
    p.add_argument("--orders", required=True, help="comma-separated order ids")
    p.add_argument("--repair", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    raise SystemExit(asyncio.run(_amain(args)))


if __name__ == "__main__":
    main()
