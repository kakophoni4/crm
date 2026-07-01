#!/usr/bin/env python3
"""Build a small OPT test application xlsx using lavki from opt_units_vane.json.

Usage:
  py scripts/opt_build_test_zayavka.py
  py scripts/opt_build_test_zayavka.py --buyer-inn 5507266215 --out scripts/fixtures/Заявка-тест-CRM.xlsx
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook

_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_JSON = _ROOT / "scripts" / "opt_units_vane.json"
_DEFAULT_OUT = _ROOT / "scripts" / "fixtures" / "Заявка-тест-CRM.xlsx"

# Same buyer as sample NAVEL files — set this INN on the contact card before upload.
DEFAULT_BUYER_INN = "5507266215"
DEFAULT_AMOUNTS = (Decimal("150000"), Decimal("220500"), Decimal("98500"))


def _load_supplier_inns(json_path: Path, count: int) -> list[str]:
    units = json.loads(json_path.read_text(encoding="utf-8"))
    inns: list[str] = []
    for unit in units:
        inn = str(unit.get("inn", "")).strip()
        if inn and inn not in inns:
            inns.append(inn)
        if len(inns) >= count:
            break
    if len(inns) < count:
        raise SystemExit(f"Need at least {count} lavki in {json_path}, got {len(inns)}")
    return inns


def build_workbook(
    *,
    buyer_inn: str,
    supplier_inns: list[str],
    amounts: tuple[Decimal, ...],
    document_dates: tuple[date, ...],
) -> Workbook:
    wb = Workbook()
    ws = wb.active
    ws.title = "Заявка"

    ws["B2"] = "Ставка"
    ws["C2"] = "Ставка НДС:"
    ws["D2"] = 20
    ws["E2"] = "%"

    ws["B3"] = "ИНН Поставщик-продавец\n(лавка поставщик)"
    ws["C3"] = "ИНН Покупатель-плательщик\n(лавка покупатель)"
    ws["D3"] = "Дата с/ф\n(дата док. счета)"
    ws["E3"] = "Сумма платежа\n(руб с НДС сверху)"

    row = 4
    for idx, supplier_inn in enumerate(supplier_inns):
        ws.cell(row, 2, supplier_inn)
        ws.cell(row, 3, buyer_inn)
        ws.cell(row, 4, document_dates[idx])
        ws.cell(row, 5, float(amounts[idx]))
        row += 1

    return wb


def main() -> None:
    parser = argparse.ArgumentParser(description="Build OPT test application xlsx")
    parser.add_argument("--json", type=Path, default=_DEFAULT_JSON)
    parser.add_argument("--out", type=Path, default=_DEFAULT_OUT)
    parser.add_argument("--buyer-inn", default=DEFAULT_BUYER_INN)
    parser.add_argument("--lines", type=int, default=3)
    args = parser.parse_args()
    if args.lines < 1 or args.lines > 10:
        raise SystemExit("--lines must be between 1 and 10")

    supplier_inns = _load_supplier_inns(args.json, args.lines)
    amounts = DEFAULT_AMOUNTS[: args.lines]
    if len(amounts) < args.lines:
        amounts = amounts + (Decimal("100000"),) * (args.lines - len(amounts))

    dates = (
        date(2026, 1, 15),
        date(2026, 2, 10),
        date(2026, 3, 5),
        date(2026, 3, 20),
        date(2026, 4, 1),
    )[: args.lines]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    wb = build_workbook(
        buyer_inn=args.buyer_inn,
        supplier_inns=supplier_inns,
        amounts=amounts,
        document_dates=dates,
    )
    wb.save(args.out)

    print(f"Created {args.out}")
    print(f"Buyer INN (contact card): {args.buyer_inn}")
    print("Supplier INNs:")
    for inn in supplier_inns:
        print(f"  - {inn}")
    print("")
    print("Server: seed lavki first, then upload this file in an ОПТ deal.")


if __name__ == "__main__":
    main()
