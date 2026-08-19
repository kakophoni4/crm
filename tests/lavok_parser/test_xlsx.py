from __future__ import annotations

from io import BytesIO

from openpyxl import Workbook

from app.modules.lavok_parser.xlsx import parse_lavok_xlsx, parse_sheet_date


def test_parse_sheet_date() -> None:
    parsed = parse_sheet_date("19.08.2026")
    assert parsed is not None
    assert parsed.isoformat() == "2026-08-19"
    assert parse_sheet_date("Notes") is None


def test_parse_lavok_xlsx_upsert_keys() -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "19.08.2026"
    sheet.append(["Источник", "Название", "ИНН", "Цена", "Балл", "Итог", "Ссылка"])
    sheet.append(["группа", 'ООО "ТЕСТ"', "9703252833", 80000, 100, "Беру в работу", "https://t.me/c/1/2"])
    sheet.append(["группа", "без инн", None, 1, 0, "нет", None])
    extra = workbook.create_sheet("служебный")
    extra.append(["не дата"])
    buf = BytesIO()
    workbook.save(buf)

    rows = parse_lavok_xlsx(buf.getvalue())
    assert len(rows) == 1
    assert rows[0].inn == "9703252833"
    assert rows[0].sheet_date.isoformat() == "2026-08-19"
    assert rows[0].fields["name"] == 'ООО "ТЕСТ"'
    assert rows[0].fields["price"] == "80000"
    assert rows[0].fields["score"] == "100"
    assert rows[0].fields["summary"] == "Беру в работу"
    assert rows[0].fields["link"] == "https://t.me/c/1/2"
