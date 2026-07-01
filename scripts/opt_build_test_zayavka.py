#!/usr/bin/env python3
"""Build OPT test application xlsx (NAVEL-style layout).

Usage:
  py scripts/opt_build_test_zayavka.py
  py scripts/opt_build_test_zayavka.py --out scripts/fixtures/Заявка-тест-CRM.xlsx

Before upload on server:
  bash scripts/deploy/seed-opt-lavki.sh
  docker exec -i crm-staging-postgres psql -U crm -d crm < scripts/fixtures/seed-opt-test-lavki.sql
"""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook

_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_SPEC = _ROOT / "scripts" / "fixtures" / "opt-navel-zayavka-spec.json"
_DEFAULT_OUT = _ROOT / "scripts" / "fixtures" / "opt-test-crm.xlsx"
_DEFAULT_OUT_RU = _ROOT / "scripts" / "fixtures" / "Заявка-тест-CRM.xlsx"


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def build_workbook_from_spec(spec: dict) -> Workbook:
    wb = Workbook()
    ws = wb.active
    ws.title = str(spec.get("sheet_title") or "Заявка")

    vat_rate = spec.get("vat_rate_percent", 20)
    ws["B2"] = "Ставка"
    ws["C2"] = "Ставка НДС:"
    ws["D2"] = vat_rate
    ws["E2"] = "%"

    ws["B3"] = "ИНН Поставщик-продавец\n(лавка поставщик)"
    ws["C3"] = "ИНН Покупатель-плательщик\n(лавка покупатель)"
    ws["D3"] = "Дата с/ф\n(дата док. счета)"
    ws["E3"] = "Сумма платежа\n(руб с НДС сверху)"

    buyer_inn = str(spec["buyer"]["inn"])
    row = 4
    for line in spec["lines"]:
        ws.cell(row, 2, str(line["supplier_inn"]))
        ws.cell(row, 3, buyer_inn)
        ws.cell(row, 4, _parse_date(str(line["document_date"])))
        amount = line["amount"]
        if isinstance(amount, str):
            amount = float(Decimal(amount))
        ws.cell(row, 5, float(amount))
        row += 1

    return wb


def main() -> None:
    parser = argparse.ArgumentParser(description="Build NAVEL-style OPT test xlsx")
    parser.add_argument("--spec", type=Path, default=_DEFAULT_SPEC)
    parser.add_argument("--out", type=Path, default=_DEFAULT_OUT)
    args = parser.parse_args()

    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    wb = build_workbook_from_spec(spec)
    wb.save(args.out)
    if args.out.resolve() != _DEFAULT_OUT_RU.resolve():
        try:
            wb.save(_DEFAULT_OUT_RU)
        except OSError:
            pass

    buyer = spec["buyer"]
    print(f"Created {args.out}")
    print(f"Buyer: {buyer.get('name')} ИНН {buyer['inn']} КПП {buyer.get('kpp')}")
    print("Supplier INNs:")
    for line in spec["lines"]:
        print(f"  - {line['supplier_inn']}  {line['document_date']}  {line['amount']}")
    print("")
    print("Server: seed lavki (seed-opt-lavki.sh + seed-opt-test-lavki.sql), then upload in ОПТ deal.")


if __name__ == "__main__":
    main()
