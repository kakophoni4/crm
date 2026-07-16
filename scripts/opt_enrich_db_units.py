#!/usr/bin/env python3
"""Enrich active opt_units in the database with KPP/name from EGRUL.

Usage on VPS (inside API/worker container):
  docker exec crm-staging-api python scripts/opt_enrich_db_units.py --only-missing
  docker exec crm-staging-api python scripts/opt_enrich_db_units.py --inn 7708721010
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from sqlalchemy import select

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.modules.db.models.opt_unit import OptUnit  # noqa: E402
from app.modules.leads.opt.repository import OptOrderRepository  # noqa: E402
from app.modules.leads.opt.requisites import ensure_unit_requisites  # noqa: E402
from app.shared.db import get_session_factory  # noqa: E402


# Period rearrangements (3/25, 4/25) — enrich these after migration 0082.
REARRANGEMENT_INNS = (
    "7733419099",  # Привет — 3/25
    "7733428671",  # Иволга — 3/25
    "7733418909",  # Спектр — 4/25
    "7733430705",  # Орион — 4/25
)


async def _run(*, only_missing: bool, inns: list[str] | None) -> int:
    session_factory = get_session_factory()
    updated = 0
    skipped = 0

    async with session_factory() as session:
        repo = OptOrderRepository(session)
        stmt = select(OptUnit).where(OptUnit.is_active.is_(True)).order_by(OptUnit.inn)
        if inns:
            stmt = stmt.where(OptUnit.inn.in_(inns))
        result = await session.execute(stmt)
        units = list(result.scalars().all())

        if inns:
            found = {u.inn for u in units}
            missing = [inn for inn in inns if inn not in found]
            if missing:
                print(f"Не найдены в opt_units: {', '.join(missing)}")
                if not units:
                    return 1

        print(f"Обрабатываем {len(units)} лавок...")
        for idx, unit in enumerate(units, start=1):
            if only_missing and unit.kpp and unit.name and len(unit.name.strip()) >= 40:
                skipped += 1
                continue

            before_kpp = unit.kpp
            before_name = unit.name
            print(f"[{idx}/{len(units)}] {unit.inn} ({unit.name})")
            await ensure_unit_requisites(repo, unit)
            if unit.kpp != before_kpp or unit.name != before_name:
                updated += 1
                print(f"  ok kpp={unit.kpp or '-'} name={unit.name or '-'}")
            else:
                print("  без изменений")

        await session.commit()

    print(f"Готово: обновлено {updated}, пропущено {skipped}, всего {len(units)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Enrich opt_units in DB from EGRUL")
    parser.add_argument("--only-missing", action="store_true", help="Skip rows with kpp and long name")
    parser.add_argument("--inn", action="append", dest="inns", help="Process INN (repeatable)")
    parser.add_argument(
        "--rearrangements",
        action="store_true",
        help="Enrich period rearrangement lavkas (Привет/Иволга/Спектр/Орион)",
    )
    args = parser.parse_args()
    inns = list(args.inns or [])
    if args.rearrangements:
        inns.extend(REARRANGEMENT_INNS)
    return asyncio.run(_run(only_missing=args.only_missing, inns=inns or None))


if __name__ == "__main__":
    raise SystemExit(main())
