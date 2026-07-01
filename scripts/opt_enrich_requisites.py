#!/usr/bin/env python3
"""Fetch KPP + legal name from FNS EGRUL for all lavki and known buyers.

Usage:
  py scripts/opt_enrich_requisites.py
  py scripts/opt_enrich_requisites.py --only-missing
  py scripts/opt_enrich_requisites.py --sql scripts/deploy/seed-opt-lavki.sql

Updates scripts/opt_units_vane.json and regenerates seed SQL with kpp/name.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.modules.leads.opt.egrul import lookup_party_by_inn_sync  # noqa: E402

_DEFAULT_JSON = _ROOT / "scripts" / "opt_units_vane.json"
_DEFAULT_BUYERS = _ROOT / "app" / "modules" / "leads" / "opt" / "data" / "opt-known-buyers.json"
_DEFAULT_SQL = _ROOT / "scripts" / "deploy" / "seed-opt-lavki.sql"


def _enrich_unit(unit: dict[str, str], *, force: bool) -> dict[str, str]:
    inn = unit["inn"]
    if not force and unit.get("kpp") and unit.get("legal_name"):
        return unit
    party = lookup_party_by_inn_sync(inn)
    if party is None:
        print(f"  skip {inn} — not found in EGRUL")
        return unit
    updated = dict(unit)
    if party.kpp:
        updated["kpp"] = party.kpp
    updated["legal_name"] = party.name
    print(f"  ok {inn} kpp={party.kpp}")
    return updated


def write_sql(units: list[dict[str, str]], path: Path) -> None:
    lines = [
        "-- Upsert lavki from opt_units_vane.json (with KPP from EGRUL)",
        "-- Run on server:",
        "--   docker exec -i crm-staging-postgres psql -U crm -d crm < scripts/deploy/seed-opt-lavki.sql",
        "",
    ]
    for unit in units:
        inn = unit["inn"]
        name = (unit.get("legal_name") or unit["name"]).replace("'", "''")
        kpp = unit.get("kpp")
        kpp_sql = "NULL" if not kpp else f"'{kpp}'"
        lines.append(
            "INSERT INTO opt_units (inn, kpp, name, category_code, is_active)\n"
            f"VALUES ('{inn}', {kpp_sql}, '{name}', 'TECH', TRUE)\n"
            "ON CONFLICT (inn) DO UPDATE SET\n"
            "  kpp = COALESCE(EXCLUDED.kpp, opt_units.kpp),\n"
            "  name = EXCLUDED.name,\n"
            "  category_code = COALESCE(opt_units.category_code, 'TECH'),\n"
            "  is_active = TRUE;"
        )
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def enrich_buyers(path: Path, *, force: bool) -> None:
    if not path.is_file():
        return
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return
    changed = 0
    for inn, row in raw.items():
        if not isinstance(row, dict):
            continue
        if not force and row.get("kpp") and row.get("name"):
            continue
        party = lookup_party_by_inn_sync(str(inn))
        if party is None:
            print(f"  buyer skip {inn}")
            continue
        if party.kpp:
            row["kpp"] = party.kpp
        if party.name:
            row["name"] = party.name
        changed += 1
        print(f"  buyer ok {inn}")
    path.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Updated {changed} buyers in {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich OPT lavki/buyers with KPP from EGRUL")
    parser.add_argument("--json", type=Path, default=_DEFAULT_JSON)
    parser.add_argument("--buyers", type=Path, default=_DEFAULT_BUYERS)
    parser.add_argument("--sql", type=Path, default=_DEFAULT_SQL)
    parser.add_argument("--force", action="store_true", help="Re-fetch even if kpp exists")
    parser.add_argument("--only-missing", action="store_true", help="Only INNs without kpp")
    args = parser.parse_args()
    force = args.force and not args.only_missing

    units = json.loads(args.json.read_text(encoding="utf-8"))
    print(f"Enriching {len(units)} lavki...")
    enriched: list[dict[str, str]] = []
    for idx, unit in enumerate(units, start=1):
        if args.only_missing and unit.get("kpp"):
            enriched.append(unit)
            continue
        print(f"[{idx}/{len(units)}] {unit['inn']}")
        enriched.append(_enrich_unit(unit, force=force))

    args.json.write_text(json.dumps(enriched, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.json}")

    if args.sql is not None:
        write_sql(enriched, args.sql)
        print(f"Wrote {args.sql}")

    print("Enriching known buyers...")
    enrich_buyers(args.buyers, force=force)


if __name__ == "__main__":
    main()
