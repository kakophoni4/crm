#!/usr/bin/env python3
"""Create missing opt_units and fill KPP/name from FNS EGRUL.

Usage on VPS (API container needs outbound HTTPS to egrul.nalog.ru):

  docker exec crm-staging-api python scripts/opt_add_missing_units_egrul.py
  docker exec crm-staging-api python scripts/opt_add_missing_units_egrul.py --dry-run
  docker exec crm-staging-api python scripts/opt_add_missing_units_egrul.py --inn 7707795812

Defaults for new rows:
  category_code=TECH, commission=1.3%, period=2/26
  is_active=false if Excel label contains "не на связи", else true
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.modules.db.models.opt_unit import OptUnit  # noqa: E402
from app.modules.db.models.opt_unit_period import OptUnitPeriodAvailability  # noqa: E402
from app.modules.leads.opt.egrul import lookup_party_by_inn  # noqa: E402
from app.modules.leads.opt.tariffs import OPT_CATEGORY_TECH, OPT_CATEGORY_BASE_RATES  # noqa: E402
from app.shared.db import get_session_factory  # noqa: E402

# INN -> Excel label (from «КОМПАНИИ В СРМ»)
MISSING_FROM_XLSX: dict[str, str] = {
    "7707795812": 'ООО РЕТЕКС',
    "7708413375": 'ООО "Продмаркет" (не на связи)',
    "7716949498": 'ООО "ПБС"',
    "7724864960": "ПРЕМИУМ ИНТЕРНЭШНЛ (не на связи)",
    "7726418680": 'ООО "Бравос" (не на связи)',
    "7728324349": "ПРОМАТОМСНАБ (не на связи)",
    "7733362702": "ГРУППА ПРЕКА ООО (не на связи)",
    "7733406614": "Мика (не на связи)",
    "7733412061": "АЗАРТ",
    "7734474060": "Космо (не на связи)",
    "7751375824": "ЭРА ООО",
    "9709054034": 'ООО "Идеалиста" (не на связи)',
    "9715519249": "ПРЕМЬЕР ООО",
    "9718288381": "ЛЮКСИ ООО",
    "9724231190": "ПРОКСИ ООО",
    "9725197181": "ВЕК ООО",
}

DEFAULT_PERIOD = "2/26"
DEFAULT_RATE = OPT_CATEGORY_BASE_RATES[OPT_CATEGORY_TECH]


def _is_active_from_label(label: str) -> bool:
    return "не на связи" not in label.casefold()


async def _run(*, inns: list[str], dry_run: bool, period_code: str) -> int:
    targets = inns or list(MISSING_FROM_XLSX.keys())
    session_factory = get_session_factory()
    created = 0
    updated = 0
    failed = 0

    async with session_factory() as session:
        existing = {
            row.inn: row
            for row in (
                await session.execute(select(OptUnit).where(OptUnit.inn.in_(targets)))
            ).scalars().all()
        }

        for inn in targets:
            label = MISSING_FROM_XLSX.get(inn, inn)
            print(f"--- {inn} ({label}) ---")
            party = await lookup_party_by_inn(inn)
            if party is None:
                print("  EGRUL: not found")
                failed += 1
                continue
            print(f"  EGRUL: kpp={party.kpp or '-'} name={party.name}")

            unit = existing.get(inn)
            if unit is None:
                unit = OptUnit(
                    inn=inn,
                    kpp=party.kpp,
                    name=party.name,
                    category_code=OPT_CATEGORY_TECH,
                    commission_rate_percent=DEFAULT_RATE,
                    is_active=_is_active_from_label(label),
                )
                if dry_run:
                    print(
                        f"  dry-run CREATE active={unit.is_active} "
                        f"rate={DEFAULT_RATE} period={period_code}"
                    )
                else:
                    session.add(unit)
                    await session.flush()
                    session.add(
                        OptUnitPeriodAvailability(
                            inn=inn,
                            period_code=period_code,
                            unit_id=unit.id,
                        ),
                    )
                    print(f"  CREATED id={unit.id} active={unit.is_active}")
                created += 1
            else:
                changed = False
                if not (unit.kpp and str(unit.kpp).strip()) and party.kpp:
                    unit.kpp = party.kpp
                    changed = True
                if party.name and (
                    not unit.name
                    or len(unit.name.strip()) < 40
                    or not unit.name.casefold().startswith("общество")
                ):
                    unit.name = party.name
                    changed = True
                if dry_run:
                    print(f"  dry-run UPDATE changed={changed}")
                elif changed:
                    print("  UPDATED requisites")
                    updated += 1
                else:
                    print("  already present, no change")

        if not dry_run:
            await session.commit()

    print(f"Done: created={created} updated={updated} egrul_failed={failed}")
    return 1 if failed and created == 0 and updated == 0 else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Add missing opt_units with EGRUL requisites")
    parser.add_argument("--inn", action="append", dest="inns", help="INN to process (repeatable)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--period", default=DEFAULT_PERIOD, help="Period code for new units")
    args = parser.parse_args()
    return asyncio.run(_run(inns=list(args.inns or []), dry_run=args.dry_run, period_code=args.period))


if __name__ == "__main__":
    raise SystemExit(main())
