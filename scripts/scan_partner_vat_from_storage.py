#!/usr/bin/env python3
"""Scan CRM storage for partner Forma_zayavki xlsx and print VAT totals.

Discovers spreadsheet keys from DB (uploaded_files / group_chat_files / message
attachments), downloads from MinIO, keeps only partner-form layout, aggregates.

Run on VPS inside api container:
  docker cp scripts/analyze_partner_registry.py crm-staging-api:/tmp/
  docker cp scripts/scan_partner_vat_from_storage.py crm-staging-api:/tmp/
  docker exec -i crm-staging-api python /tmp/scan_partner_vat_from_storage.py
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

# Allow `docker cp` both scripts into /tmp
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, "/tmp")

from sqlalchemy import text  # noqa: E402

from analyze_partner_registry import (  # noqa: E402
    FileResult,
    analyze_file,
    fmt_money,
    print_report,
)
from app.shared.db import get_session_factory  # noqa: E402
from app.shared.storage import get_file_storage  # noqa: E402


async def _collect_candidates() -> list[tuple[str, str]]:
    """Return list of (storage_key, display_name)."""
    session_factory = get_session_factory()
    found: dict[str, str] = {}
    async with session_factory() as session:
        q1 = await session.execute(
            text(
                """
                SELECT storage_key, original_name
                FROM uploaded_files
                WHERE lower(original_name) LIKE '%.xlsx'
                   OR lower(original_name) LIKE '%.xlsm'
                   OR lower(original_name) LIKE '%.xls'
                   OR mime_type ILIKE '%spreadsheet%'
                   OR mime_type ILIKE '%excel%'
                """
            ),
        )
        for key, name in q1.all():
            if key:
                found[str(key)] = str(name or key)

        q2 = await session.execute(
            text(
                """
                SELECT storage_key, original_name
                FROM group_chat_files
                WHERE lower(original_name) LIKE '%.xlsx'
                   OR lower(original_name) LIKE '%.xlsm'
                   OR lower(original_name) LIKE '%.xls'
                   OR mime_type ILIKE '%spreadsheet%'
                   OR mime_type ILIKE '%excel%'
                """
            ),
        )
        for key, name in q2.all():
            if key:
                found.setdefault(str(key), str(name or key))

        q3 = await session.execute(
            text(
                """
                SELECT
                  att->>'storage_key' AS storage_key,
                  COALESCE(att->>'filename', att->>'name', 'attachment.xlsx') AS original_name
                FROM messages m
                CROSS JOIN LATERAL jsonb_array_elements(
                  CASE WHEN jsonb_typeof(m.attachments) = 'array' THEN m.attachments ELSE '[]'::jsonb END
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
                """
            ),
        )
        for key, name in q3.all():
            if key:
                found.setdefault(str(key), str(name or key))

        q4 = await session.execute(
            text(
                """
                SELECT DISTINCT o.source_filename
                FROM lead_opt_orders o
                WHERE o.source_filename IS NOT NULL
                  AND (
                    lower(o.source_filename) LIKE '%.xlsx'
                    OR lower(o.source_filename) LIKE '%.xlsm'
                  )
                """
            ),
        )
        # source_filename alone is not a storage key — just for logging interest
        opt_names = [str(r[0]) for r in q4.all() if r[0]]
        if opt_names:
            print(f"(info) lead_opt_orders source files mentioned: {len(opt_names)}", flush=True)

    return sorted(found.items(), key=lambda x: x[1].lower())


async def _download_all(candidates: list[tuple[str, str]], workdir: Path) -> list[Path]:
    storage = get_file_storage()
    paths: list[Path] = []
    ok = 0
    fail = 0
    for idx, (key, name) in enumerate(candidates, 1):
        safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in name)[:120]
        dest = workdir / f"{idx:04d}_{safe}"
        if not dest.suffix:
            dest = dest.with_suffix(".xlsx")
        try:
            data, _ctype = await storage.get_bytes(key)
            dest.write_bytes(data)
            paths.append(dest)
            ok += 1
        except Exception as exc:  # noqa: BLE001
            fail += 1
            print(f"  skip download [{idx}/{len(candidates)}] {name}: {exc}", flush=True)
        if idx % 25 == 0:
            print(f"  downloaded {idx}/{len(candidates)}...", flush=True)
    print(f"Downloads: ok={ok} fail={fail}", flush=True)
    return paths


async def _amain() -> int:
    print("Collecting spreadsheet keys from DB...", flush=True)
    candidates = await _collect_candidates()
    print(f"Candidates: {len(candidates)}", flush=True)
    if not candidates:
        print("No xlsx/xls found in uploaded_files / group_chat_files / message attachments.")
        return 1

    with tempfile.TemporaryDirectory(prefix="partner-vat-") as tmp:
        workdir = Path(tmp)
        print(f"Downloading into {workdir} ...", flush=True)
        paths = await _download_all(candidates, workdir)
        if not paths:
            print("Nothing downloaded.")
            return 1

        print("Analyzing...", flush=True)
        results: list[FileResult] = [analyze_file(p) for p in paths]
        csv_path = Path("/tmp/partner_vat_from_storage.csv")
        print_report(
            results,
            by_org=True,
            by_file=True,
            csv_path=csv_path,
            dedupe=True,
        )

        partner_n = sum(1 for r in results if r.kind == "partner")
        print()
        print(f"Done. Partner forms matched: {partner_n} / {len(results)} files")
        print(f"CSV: {csv_path}")
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(_amain()))


if __name__ == "__main__":
    main()
