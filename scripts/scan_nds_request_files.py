#!/usr/bin/env python3
"""Scan storage Excel files that look like «ЗАПРОС НДС» and sum CRM «к оплате».

Detection is by workbook CONTENT only (headers: ИНН покупателя /
Стоимость покупки / ИНН продавца) — filenames are ignored.

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


async def _scan_local(path: Path, units: dict[str, OptUnit]) -> list[FileHit]:
    content = path.read_bytes()
    parsed = parse_nds_request_workbook(content)
    if not parsed.matched or parsed.application is None:
        print(f"NOT MATCHED (by content): {path.name} ({parsed.reason})")
        return []
    volume, commission = _price(parsed.application, units)
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
        ),
    ]


async def _scan_storage(*, limit: int | None) -> tuple[list[FileHit], int, int, int]:
    units = await _load_units()
    candidates = await _collect_candidates(limit=limit)
    storage = get_file_storage()
    hits: list[FileHit] = []
    scanned = 0
    errors = 0
    empty_templates = 0

    print(
        f"Candidates (xlsx/xls from uploaded_files + group_chat_files "
        f"+ message attachments): {len(candidates)}",
        flush=True,
    )
    print("Matching by CONTENT headers only (filename ignored).", flush=True)

    for cand in candidates:
        scanned += 1
        try:
            content, _ctype = await storage.get_bytes(cand.storage_key)
        except Exception as exc:  # noqa: BLE001
            errors += 1
            print(f"DOWNLOAD FAIL source={cand.source} name={cand.name!r}: {exc}")
            continue
        parsed = parse_nds_request_workbook(content)
        if not parsed.matched:
            continue
        if parsed.application is None:
            empty_templates += 1
            print(
                f"EMPTY TEMPLATE source={cand.source} name={cand.name!r} "
                f"sheet={parsed.sheet_name!r} ({parsed.reason})",
            )
            continue
        volume, commission = _price(parsed.application, units)
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
            ),
        )
        print(
            f"HIT source={cand.source} buyer={parsed.application.buyer_inn} "
            f"lines={len(parsed.application.lines)} "
            f"volume={_money(volume)} commission={_money(commission)} "
            f"name={cand.name!r}",
        )

    return hits, scanned, errors, empty_templates


async def _run(*, local_file: str | None, limit: int | None) -> int:
    units = await _load_units()
    empty_templates = 0
    if local_file:
        hits = await _scan_local(Path(local_file), units)
        scanned = 1
        errors = 0
    else:
        hits, scanned, errors, empty_templates = await _scan_storage(limit=limit)

    print("")
    print("=== SUMMARY ===")
    print(f"scanned_spreadsheets: {scanned}")
    print(f"matched_with_data (content): {len(hits)}")
    print(f"empty_templates (content match, no rows): {empty_templates}")
    print(f"download_errors: {errors}")
    total_volume = sum((h.volume for h in hits), Decimal("0"))
    total_commission = sum((h.commission for h in hits), Decimal("0"))
    print(f"total_volume (стоимость покупок): {_money(total_volume)} ₽")
    print(f"total_commission (к оплате CRM):  {_money(total_commission)} ₽")
    if hits:
        print("")
        print("per file:")
        for hit in hits:
            print(
                f"  - [{hit.source}] buyer={hit.buyer_inn} lines={hit.lines} "
                f"volume={_money(hit.volume)} к_оплате={_money(hit.commission)} "
                f"| {hit.name}",
            )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scan ЗАПРОС НДС files in storage by CONTENT (not filename)",
    )
    parser.add_argument("--local-file", help="Parse a single local xlsx instead of storage")
    parser.add_argument("--limit", type=int, default=None, help="Max spreadsheet candidates")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_run(local_file=args.local_file, limit=args.limit)))


if __name__ == "__main__":
    main()
