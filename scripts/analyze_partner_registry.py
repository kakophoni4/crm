#!/usr/bin/env python3
"""Aggregate VAT from partner Forma_zayavki-style Excel files (NOT CRM registry).

Partner form headers look like:
  Наименование покупателя | ИНН Покупателя | Сумма (в т.ч. НДС) | Сумма НДС | ИНН Организации | ...

CRM registry (skip) looks like:
  № документа | Покупатель | Поставщик | Сумма | Сумма НДС | Сумма без НДС

Usage (local):
  python scripts/analyze_partner_registry.py "C:\\path\\to\\folder"
  python scripts/analyze_partner_registry.py /data/partner-forms --by-org --by-file

Usage (VPS):
  mkdir -p /tmp/partner-forms
  # положить туда все Forma_zayavki*.xlsx
  docker cp scripts/analyze_partner_registry.py crm-staging-api:/tmp/analyze_partner_registry.py
  docker cp /tmp/partner-forms crm-staging-api:/tmp/partner-forms
  docker exec -i crm-staging-api python /tmp/analyze_partner_registry.py /tmp/partner-forms --by-org
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path

try:
    import openpyxl
except ImportError:
    print("Need openpyxl: pip install openpyxl", file=sys.stderr)
    raise SystemExit(1)


def parse_money(value: object) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value))
    text = str(value).strip().replace("\xa0", "").replace(" ", "")
    if not text:
        return None
    text = text.replace(",", ".")
    text = re.sub(r"[^\d.\-]", "", text)
    if not text or text in {".", "-", "-."}:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def norm_header(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


PARTNER_ALIASES: dict[str, tuple[str, ...]] = {
    "buyer_name": ("наименование покупателя",),
    "buyer_inn": ("инн покупателя",),
    "date": ("дата (дд.мм.гг)", "дата"),
    "amount_with_vat": ("сумма (в т.ч. ндс)", "сумма в т.ч. ндс"),
    "vat_amount": ("сумма ндс",),
    "org_inn": ("инн организации",),
    "org_name": ("наименование организации",),
    "doc_no": ("№ реализации", "номер реализации"),
}

# Strong signals that this is CRM OPT registry export — skip.
CRM_REGISTRY_MARKERS = (
    "№ документа",
    "сумма без ндс",
    "инн поставщика",
    "кпп поставщика",
)


@dataclass
class DataRow:
    source_file: str
    buyer_name: str
    buyer_inn: str
    org_name: str
    org_inn: str
    date: str
    doc_no: str
    amount_with_vat: Decimal
    vat_amount: Decimal


@dataclass
class FileResult:
    path: Path
    kind: str  # partner | crm_registry | unknown | error
    rows: list[DataRow] = field(default_factory=list)
    error: str | None = None


def map_headers(header_row: tuple[object, ...], aliases: dict[str, tuple[str, ...]]) -> dict[str, int]:
    by_norm = {norm_header(cell): idx for idx, cell in enumerate(header_row) if cell}
    mapping: dict[str, int] = {}
    for key, names in aliases.items():
        for alias in names:
            if alias in by_norm:
                mapping[key] = by_norm[alias]
                break
    return mapping


def detect_kind(header_row: tuple[object, ...]) -> str:
    norms = {norm_header(c) for c in header_row if c}
    if any(norm_header(m) in norms for m in CRM_REGISTRY_MARKERS):
        # CRM registry also has «Сумма НДС» — exclude explicitly
        if "поставщик" in norms or "сумма без ндс" in norms or "№ документа" in norms:
            return "crm_registry"
    partner_hits = 0
    if "сумма ндс" in norms:
        partner_hits += 1
    if "наименование покупателя" in norms or "инн покупателя" in norms:
        partner_hits += 1
    if "инн организации" in norms or "наименование организации" in norms:
        partner_hits += 1
    if "сумма (в т.ч. ндс)" in norms or "сумма в т.ч. ндс" in norms:
        partner_hits += 1
    if partner_hits >= 2 and "сумма ндс" in norms:
        return "partner"
    return "unknown"


def cell(row: tuple[object, ...], idx: int | None) -> object:
    if idx is None or idx >= len(row):
        return None
    return row[idx]


def parse_partner_sheet(path: Path, header: tuple[object, ...], data_rows: list[tuple]) -> list[DataRow]:
    cols = map_headers(header, PARTNER_ALIASES)
    if "vat_amount" not in cols:
        return []
    out: list[DataRow] = []
    rel = path.name
    for raw in data_rows:
        if not any(v is not None and str(v).strip() != "" for v in raw):
            continue
        vat = parse_money(cell(raw, cols.get("vat_amount")))
        amount = parse_money(cell(raw, cols.get("amount_with_vat")))
        if vat is None and amount is None:
            continue
        # skip total-like rows without buyer/org
        buyer = str(cell(raw, cols.get("buyer_name")) or "").strip()
        org = str(cell(raw, cols.get("org_name")) or "").strip()
        if not buyer and not org and (vat == 0 or vat is None):
            continue
        out.append(
            DataRow(
                source_file=rel,
                buyer_name=buyer,
                buyer_inn=str(cell(raw, cols.get("buyer_inn")) or "").strip(),
                org_name=org,
                org_inn=str(cell(raw, cols.get("org_inn")) or "").strip(),
                date=str(cell(raw, cols.get("date")) or "").strip(),
                doc_no=str(cell(raw, cols.get("doc_no")) or "").strip(),
                amount_with_vat=amount or Decimal("0"),
                vat_amount=vat or Decimal("0"),
            ),
        )
    return out


def analyze_file(path: Path) -> FileResult:
    try:
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
        ws = wb.active
        it = ws.iter_rows(values_only=True)
        header = next(it, None)
        if not header:
            return FileResult(path=path, kind="unknown", error="empty")
        header_t = tuple(header)
        kind = detect_kind(header_t)
        if kind != "partner":
            return FileResult(path=path, kind=kind)
        data = [tuple(r) for r in it]
        rows = parse_partner_sheet(path, header_t, data)
        return FileResult(path=path, kind="partner", rows=rows)
    except Exception as exc:  # noqa: BLE001 — console tool
        return FileResult(path=path, kind="error", error=str(exc)[:300])


def iter_xlsx(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    files: list[Path] = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        name = p.name.lower()
        if name.endswith((".xlsx", ".xlsm")) and not name.startswith("~$"):
            files.append(p)
    return files


def fmt_money(value: Decimal) -> str:
    return f"{value:,.2f}".replace(",", " ").replace(".", ",")


def print_report(
    results: list[FileResult],
    *,
    by_org: bool,
    by_file: bool,
    csv_path: Path | None,
) -> None:
    partner = [r for r in results if r.kind == "partner"]
    skipped = [r for r in results if r.kind in {"crm_registry", "unknown"}]
    errors = [r for r in results if r.kind == "error"]
    rows = [row for fr in partner for row in fr.rows]

    total_vat = sum((r.vat_amount for r in rows), Decimal("0"))
    total_amount = sum((r.amount_with_vat for r in rows), Decimal("0"))

    print("=== Партнёрские формы (Forma_zayavki) ===")
    print(f"Файлов найдено:     {len(results)}")
    print(f"  партнёрских:      {len(partner)}")
    print(f"  пропущено (CRM/другое): {len(skipped)}")
    print(f"  ошибок чтения:    {len(errors)}")
    print(f"Строк данных:       {len(rows)}")
    print(f"Сумма (в т.ч. НДС): {fmt_money(total_amount)}")
    print(f"Сумма НДС:          {fmt_money(total_vat)}")
    print()

    if by_file:
        print("=== По файлам ===")
        for fr in partner:
            vat = sum((r.vat_amount for r in fr.rows), Decimal("0"))
            amount = sum((r.amount_with_vat for r in fr.rows), Decimal("0"))
            print(f"{fr.path.name}: строк={len(fr.rows)} сумма={fmt_money(amount)} НДС={fmt_money(vat)}")
        print()

    if by_org:
        groups: dict[str, list[DataRow]] = defaultdict(list)
        for row in rows:
            key = row.org_name or row.org_inn or "без организации"
            groups[key].append(row)
        print("=== По организациям ===")
        for name in sorted(groups, key=lambda k: (-sum(r.vat_amount for r in groups[k]), k)):
            g = groups[name]
            vat = sum((r.vat_amount for r in g), Decimal("0"))
            amount = sum((r.amount_with_vat for r in g), Decimal("0"))
            print(f"{name}")
            print(f"  строк={len(g)}  сумма={fmt_money(amount)}  НДС={fmt_money(vat)}")
        print()

    if skipped:
        print("=== Пропущены (не партнёрская форма) ===")
        for fr in skipped[:30]:
            print(f"  [{fr.kind}] {fr.path.name}")
        if len(skipped) > 30:
            print(f"  ... ещё {len(skipped) - 30}")
        print()

    if errors:
        print("=== Ошибки ===")
        for fr in errors:
            print(f"  {fr.path.name}: {fr.error}")
        print()

    print("=== Общий список строк ===")
    for i, row in enumerate(rows, 1):
        label = row.buyer_name or row.buyer_inn or row.doc_no or f"#{i}"
        print(
            f"{i:>4}. [{row.source_file}] {label[:36]:<36}  "
            f"сумма={fmt_money(row.amount_with_vat):>14}  "
            f"НДС={fmt_money(row.vat_amount):>14}",
        )

    if csv_path is not None:
        with csv_path.open("w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh, delimiter=";")
            w.writerow(
                [
                    "file",
                    "org_name",
                    "org_inn",
                    "buyer_name",
                    "buyer_inn",
                    "date",
                    "doc_no",
                    "amount_with_vat",
                    "vat_amount",
                ],
            )
            for row in rows:
                w.writerow(
                    [
                        row.source_file,
                        row.org_name,
                        row.org_inn,
                        row.buyer_name,
                        row.buyer_inn,
                        row.date,
                        row.doc_no,
                        str(row.amount_with_vat),
                        str(row.vat_amount),
                    ],
                )
        print()
        print(f"CSV: {csv_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Свод НДС по партнёрским Forma_zayavki (не CRM-реестр)",
    )
    parser.add_argument(
        "path",
        help="Файл .xlsx или папка с файлами",
    )
    parser.add_argument("--by-org", action="store_true", help="Группировка по организации")
    parser.add_argument("--by-file", action="store_true", help="Итог по каждому файлу")
    parser.add_argument("--csv", type=str, default="", help="Путь для CSV общего списка")
    args = parser.parse_args()

    root = Path(args.path)
    if not root.exists():
        raise SystemExit(f"Не найдено: {root}")

    files = iter_xlsx(root)
    if not files:
        raise SystemExit(f"Нет .xlsx в {root}")

    results = [analyze_file(p) for p in files]
    csv_path = Path(args.csv) if args.csv else None
    print_report(results, by_org=args.by_org, by_file=args.by_file, csv_path=csv_path)


if __name__ == "__main__":
    main()
