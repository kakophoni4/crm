#!/usr/bin/env python3
"""Scan storage for partner applications and sum CRM «к оплате».

Detection by CONTENT only (not filename):
  - nds_request: Заявка на НДС (стоимость покупки / ИНН продавца)
  - partner_forma: Forma_zayavki (сумма в т.ч. НДС / ИНН организации)

OPT upload format and CRM registry exports are skipped on purpose.

Sources (deduped by storage_key):
  - uploaded_files
  - group_chat_files
  - message attachments (JSON)

Usage on VPS:
  docker exec crm-staging-api python scripts/scan_nds_request_files.py
  docker exec crm-staging-api python scripts/scan_nds_request_files.py --limit 50
  docker exec crm-staging-api python scripts/scan_nds_request_files.py --local-file /tmp/file.xlsx
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select, text

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.modules.db.models.opt_unit import OptUnit  # noqa: E402
from app.modules.leads.opt.nds_request_parser import (  # noqa: E402
    lines_for_pricing,
    parse_nds_request_workbook,
)
from app.modules.leads.opt.pricing import compute_order_pricing  # noqa: E402
from app.shared.db import get_session_factory  # noqa: E402
from app.shared.storage import get_file_storage  # noqa: E402


@dataclass
class FileHit:
    source: str
    name: str
    storage_key: str | None
    buyer_inn: str
    lines: int
    volume: Decimal
    commission: Decimal
    sheet_name: str | None
    form_kind: str | None


@dataclass(frozen=True)
class Candidate:
    storage_key: str
    name: str
    source: str


def _money(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01')):,.2f}".replace(",", " ")


async def _load_units() -> dict[str, OptUnit]:
    session_factory = get_session_factory()
    async with session_factory() as session:
        orm_rows = (await session.execute(select(OptUnit))).scalars().all()
        return {str(unit.inn): unit for unit in orm_rows}


def _price(application, units: dict[str, OptUnit]) -> tuple[Decimal, Decimal]:
    volume, commission, _breakdown = compute_order_pricing(
        lines_for_pricing(application),
        units,
    )
    return volume, commission


async def _collect_candidates(*, limit: int | None) -> list[Candidate]:
    """All spreadsheet-like objects in DB, deduped by storage_key."""
    session_factory = get_session_factory()
    found: dict[str, Candidate] = {}

    async with session_factory() as session:
        queries: list[tuple[str, str]] = [
            (
                "uploaded_files",
                """
                SELECT storage_key, original_name AS name, 'uploaded_files' AS source
                FROM uploaded_files
                WHERE lower(original_name) LIKE '%.xlsx'
                   OR lower(original_name) LIKE '%.xlsm'
                   OR lower(original_name) LIKE '%.xls'
                   OR mime_type ILIKE '%spreadsheet%'
                   OR mime_type ILIKE '%excel%'
                ORDER BY id DESC
                """,
            ),
            (
                "group_chat_files",
                """
                SELECT storage_key, original_name AS name, 'group_chat_files' AS source
                FROM group_chat_files
                WHERE lower(original_name) LIKE '%.xlsx'
                   OR lower(original_name) LIKE '%.xlsm'
                   OR lower(original_name) LIKE '%.xls'
                   OR mime_type ILIKE '%spreadsheet%'
                   OR mime_type ILIKE '%excel%'
                ORDER BY id DESC
                """,
            ),
            (
                "message_attachments",
                """
                SELECT
                  att->>'storage_key' AS storage_key,
                  COALESCE(att->>'filename', att->>'name', 'attachment.xlsx') AS name,
                  'message_attachments' AS source
                FROM messages m
                CROSS JOIN LATERAL jsonb_array_elements(
                  CASE WHEN jsonb_typeof(m.attachments) = 'array'
                       THEN m.attachments ELSE '[]'::jsonb END
                ) AS att
                WHERE att->>'storage_key' IS NOT NULL
                  AND att->>'storage_key' <> ''
                  AND (
                    lower(COALESCE(att->>'filename', att->>'name', '')) LIKE '%.xlsx'
                    OR lower(COALESCE(att->>'filename', att->>'name', '')) LIKE '%.xlsm'
                    OR lower(COALESCE(att->>'filename', att->>'name', '')) LIKE '%.xls'
                    OR lower(COALESCE(att->>'mime', '')) LIKE '%spreadsheet%'
                    OR lower(COALESCE(att->>'mime', '')) LIKE '%excel%'
                  )
                """,
            ),
        ]

        for _label, sql in queries:
            rows = (await session.execute(text(sql))).mappings().all()
            for row in rows:
                key = str(row["storage_key"] or "").strip()
                if not key or key in found:
                    continue
                found[key] = Candidate(
                    storage_key=key,
                    name=str(row["name"] or key),
                    source=str(row["source"]),
                )

    items = list(found.values())
    # Prefer recently-seen sources already ordered in SQL; keep stable by name
    items.sort(key=lambda c: c.name.lower())
    if limit is not None:
        items = items[:limit]
    return items


def _log(msg: str) -> None:
    print(msg, flush=True)


async def _scan_local(path: Path, units: dict[str, OptUnit]) -> list[FileHit]:
    content = path.read_bytes()
    parsed = parse_nds_request_workbook(content)
    if not parsed.matched or parsed.application is None:
        _log(f"[1/1 100%] [local] {path.name!r} → SKIP ({parsed.reason})")
        return []
    volume, commission = _price(parsed.application, units)
    _log(
        f"[1/1 100%] [local] {path.name!r} → HIT kind={parsed.form_kind} "
        f"buyer={parsed.application.buyer_inn} "
        f"lines={len(parsed.application.lines)} volume={_money(volume)} "
        f"commission={_money(commission)}",
    )
    return [
        FileHit(
            source="local",
            name=path.name,
            storage_key=None,
            buyer_inn=parsed.application.buyer_inn,
            lines=len(parsed.application.lines),
            volume=volume,
            commission=commission,
            sheet_name=parsed.sheet_name,
            form_kind=parsed.form_kind,
        ),
    ]


async def _scan_storage(
    *,
    limit: int | None,
    verbose_skip: bool,
) -> tuple[list[FileHit], int, int, int]:
    units = await _load_units()
    candidates = await _collect_candidates(limit=limit)
    storage = get_file_storage()
    hits: list[FileHit] = []
    scanned = 0
    errors = 0
    empty_templates = 0
    skipped = 0
    total = len(candidates)
    running_commission = Decimal("0")

    _log(
        f"Candidates (xlsx/xls from uploaded_files + group_chat_files "
        f"+ message attachments): {total}",
    )
    _log("Matching by CONTENT headers only (filename ignored).")
    _log(f"Progress: every file logged as [n/{total}] STATUS ...")

    for cand in candidates:
        scanned += 1
        pct = (100 * scanned) // total if total else 100
        prefix = f"[{scanned}/{total} {pct}%] [{cand.source}] {cand.name!r}"
        _log(f"{prefix} … processing")

        try:
            content, _ctype = await storage.get_bytes(cand.storage_key)
        except Exception as exc:  # noqa: BLE001
            errors += 1
            _log(f"{prefix} → DOWNLOAD_FAIL ({exc})")
            continue

        parsed = parse_nds_request_workbook(content)
        if not parsed.matched:
            skipped += 1
            reason = parsed.reason or "header_not_found"
            # Always show why — silent SKIP is confusing for ops.
            _log(f"{prefix} → SKIP ({reason})")
            continue

        if parsed.application is None:
            empty_templates += 1
            _log(
                f"{prefix} → EMPTY kind={parsed.form_kind} sheet={parsed.sheet_name!r} "
                f"({parsed.reason})",
            )
            continue

        volume, commission = _price(parsed.application, units)
        running_commission += commission
        hits.append(
            FileHit(
                source=cand.source,
                name=cand.name,
                storage_key=cand.storage_key,
                buyer_inn=parsed.application.buyer_inn,
                lines=len(parsed.application.lines),
                volume=volume,
                commission=commission,
                sheet_name=parsed.sheet_name,
                form_kind=parsed.form_kind,
            ),
        )
        _log(
            f"{prefix} → HIT kind={parsed.form_kind} "
            f"buyer={parsed.application.buyer_inn} "
            f"lines={len(parsed.application.lines)} "
            f"volume={_money(volume)} commission={_money(commission)} "
            f"| running_к_оплате={_money(running_commission)} "
            f"(hits={len(hits)} empty={empty_templates} skip={skipped} err={errors})",
        )

    return hits, scanned, errors, empty_templates


async def _run(
    *,
    local_file: str | None,
    limit: int | None,
    verbose_skip: bool,
) -> int:
    units = await _load_units()
    empty_templates = 0
    if local_file:
        hits = await _scan_local(Path(local_file), units)
        scanned = 1
        errors = 0
    else:
        hits, scanned, errors, empty_templates = await _scan_storage(
            limit=limit,
            verbose_skip=verbose_skip,
        )

    _log("")
    _log("=== SUMMARY ===")
    _log(f"scanned_spreadsheets: {scanned}")
    _log(f"matched_with_data (content): {len(hits)}")
    _log(f"empty_templates (content match, no rows): {empty_templates}")
    _log(f"download_errors: {errors}")
    total_volume = sum((h.volume for h in hits), Decimal("0"))
    total_commission = sum((h.commission for h in hits), Decimal("0"))
    _log(f"total_volume (стоимость покупок): {_money(total_volume)} ₽")
    _log(f"total_commission (к оплате CRM):  {_money(total_commission)} ₽")
    by_kind: dict[str, list[FileHit]] = {}
    for hit in hits:
        by_kind.setdefault(hit.form_kind or "unknown", []).append(hit)
    for kind, kind_hits in sorted(by_kind.items()):
        kv = sum((h.volume for h in kind_hits), Decimal("0"))
        kc = sum((h.commission for h in kind_hits), Decimal("0"))
        _log(
            f"  kind={kind}: files={len(kind_hits)} "
            f"volume={_money(kv)} commission={_money(kc)}",
        )
    if hits:
        _log("")
        _log("per file:")
        for hit in hits:
            _log(
                f"  - [{hit.source}] kind={hit.form_kind} buyer={hit.buyer_inn} "
                f"lines={hit.lines} volume={_money(hit.volume)} "
                f"к_оплате={_money(hit.commission)} | {hit.name}",
            )
    return 0


def main() -> None:
    # Line-buffered stdout even when redirected to a file.
    try:
        sys.stdout.reconfigure(line_buffering=True)  # type: ignore[attr-defined]
    except Exception:
        pass

    parser = argparse.ArgumentParser(
        description="Scan ЗАПРОС НДС files in storage by CONTENT (not filename)",
    )
    parser.add_argument("--local-file", help="Parse a single local xlsx instead of storage")
    parser.add_argument("--limit", type=int, default=None, help="Max spreadsheet candidates")
    parser.add_argument(
        "--verbose-skip",
        action="store_true",
        help="Print reason for SKIP lines (header_not_found etc.)",
    )
    args = parser.parse_args()
    raise SystemExit(
        asyncio.run(
            _run(
                local_file=args.local_file,
                limit=args.limit,
                verbose_skip=args.verbose_skip,
            ),
        ),
    )


if __name__ == "__main__":
    main()
