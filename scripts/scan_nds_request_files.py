#!/usr/bin/env python3
"""Scan storage Excel files that look like «ЗАПРОС НДС» and sum CRM «к оплате».

Detects by content (headers: ИНН покупателя / Стоимость покупки / ИНН продавца),
not by filename.

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

from sqlalchemy import or_, select

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.modules.db.models.opt_unit import OptUnit  # noqa: E402
from app.modules.db.models.uploaded_file import UploadedFile  # noqa: E402
from app.modules.leads.opt.nds_request_parser import (  # noqa: E402
    lines_for_pricing,
    parse_nds_request_workbook,
)
from app.modules.leads.opt.pricing import compute_order_pricing  # noqa: E402
from app.shared.db import get_session_factory  # noqa: E402
from app.shared.storage import get_file_storage  # noqa: E402


@dataclass
class FileHit:
    file_id: int | None
    name: str
    storage_key: str | None
    buyer_inn: str
    lines: int
    volume: Decimal
    commission: Decimal
    sheet_name: str | None


def _money(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01')):,.2f}".replace(",", " ")


async def _load_units() -> dict[str, OptUnit]:
    session_factory = get_session_factory()
    async with session_factory() as session:
        rows = (await session.execute(select(OptUnit))).scalars().all()
        return {str(unit.inn): unit for unit in rows}


def _price(application, units: dict[str, OptUnit]) -> tuple[Decimal, Decimal]:
    volume, commission, _breakdown = compute_order_pricing(
        lines_for_pricing(application),
        units,
    )
    return volume, commission


async def _scan_local(path: Path, units: dict[str, OptUnit]) -> list[FileHit]:
    content = path.read_bytes()
    parsed = parse_nds_request_workbook(content)
    if not parsed.matched or parsed.application is None:
        print(f"NOT MATCHED: {path.name} ({parsed.reason})")
        return []
    volume, commission = _price(parsed.application, units)
    return [
        FileHit(
            file_id=None,
            name=path.name,
            storage_key=None,
            buyer_inn=parsed.application.buyer_inn,
            lines=len(parsed.application.lines),
            volume=volume,
            commission=commission,
            sheet_name=parsed.sheet_name,
        ),
    ]


async def _list_xlsx_files(*, limit: int | None) -> list[UploadedFile]:
    session_factory = get_session_factory()
    async with session_factory() as session:
        stmt = (
            select(UploadedFile)
            .where(
                or_(
                    UploadedFile.original_name.ilike("%.xlsx"),
                    UploadedFile.original_name.ilike("%.xlsm"),
                    UploadedFile.mime_type.ilike("%spreadsheet%"),
                    UploadedFile.mime_type.ilike("%excel%"),
                ),
            )
            .order_by(UploadedFile.id.desc())
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        return list((await session.execute(stmt)).scalars().all())


async def _scan_storage(*, limit: int | None) -> tuple[list[FileHit], int, int]:
    units = await _load_units()
    files = await _list_xlsx_files(limit=limit)
    storage = get_file_storage()
    hits: list[FileHit] = []
    scanned = 0
    errors = 0

    for row in files:
        scanned += 1
        try:
            content, _ctype = await storage.get_bytes(row.storage_key)
        except Exception as exc:  # noqa: BLE001
            errors += 1
            print(f"DOWNLOAD FAIL id={row.id} name={row.original_name!r}: {exc}")
            continue
        parsed = parse_nds_request_workbook(content)
        if not parsed.matched:
            continue
        if parsed.application is None:
            print(
                f"MATCH EMPTY id={row.id} name={row.original_name!r} "
                f"sheet={parsed.sheet_name!r} ({parsed.reason})",
            )
            continue
        volume, commission = _price(parsed.application, units)
        hits.append(
            FileHit(
                file_id=int(row.id),
                name=row.original_name,
                storage_key=row.storage_key,
                buyer_inn=parsed.application.buyer_inn,
                lines=len(parsed.application.lines),
                volume=volume,
                commission=commission,
                sheet_name=parsed.sheet_name,
            ),
        )
        print(
            f"HIT id={row.id} buyer={parsed.application.buyer_inn} "
            f"lines={len(parsed.application.lines)} "
            f"volume={_money(volume)} commission={_money(commission)} "
            f"name={row.original_name!r}",
        )

    return hits, scanned, errors


async def _run(*, local_file: str | None, limit: int | None) -> int:
    units = await _load_units()
    if local_file:
        hits = await _scan_local(Path(local_file), units)
        scanned = 1
        errors = 0
    else:
        hits, scanned, errors = await _scan_storage(limit=limit)

    print("")
    print("=== SUMMARY ===")
    print(f"scanned_xlsx: {scanned}")
    print(f"matched_nds_request: {len(hits)}")
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
                f"  - id={hit.file_id} buyer={hit.buyer_inn} lines={hit.lines} "
                f"volume={_money(hit.volume)} к_оплате={_money(hit.commission)} "
                f"| {hit.name}",
            )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan ЗАПРОС НДС files in storage")
    parser.add_argument("--local-file", help="Parse a single local xlsx instead of storage")
    parser.add_argument("--limit", type=int, default=None, help="Max uploaded xlsx to scan")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_run(local_file=args.local_file, limit=args.limit)))


if __name__ == "__main__":
    main()
