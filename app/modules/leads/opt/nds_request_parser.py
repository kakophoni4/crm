"""Detect and parse client «ЗАПРОС НДС» Excel workbooks by content."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from io import BytesIO
from typing import Any

from openpyxl import load_workbook
from openpyxl.worksheet.worksheet import Worksheet

from app.modules.leads.opt.contact_buyer import normalize_inn, parse_decimal, parse_excel_date
from app.modules.leads.opt.parser import ParsedApplication, ParsedApplicationLine


@dataclass(frozen=True)
class NdsRequestParseResult:
    matched: bool
    sheet_name: str | None = None
    application: ParsedApplication | None = None
    reason: str | None = None


_HEADER_MARKERS = (
    "инн покупателя",
    "стоимость покупки",
    "инн продавца",
)


def _cell_text(value: object) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().lower().split())


def _header_map(row_values: list[object]) -> dict[str, int]:
    """Map logical fields → 1-based column index from a header row."""
    mapping: dict[str, int] = {}
    for idx, raw in enumerate(row_values, start=1):
        text = _cell_text(raw)
        if not text:
            continue
        if "инн покупателя" in text:
            mapping["buyer_inn"] = idx
        elif "инн продавца" in text or ("инн" in text and "продав" in text):
            mapping["supplier_inn"] = idx
        elif "стоимость покупки" in text or ("стоимость" in text and "ндс" in text):
            mapping["amount"] = idx
        elif "дата счета" in text or "дата счёта" in text or "дата счет" in text:
            mapping["document_date"] = idx
        elif text.startswith("наименование покупателя"):
            mapping["buyer_name"] = idx
        elif "наименование продавца" in text:
            mapping["supplier_name"] = idx
    return mapping


def _row_values(ws: Worksheet, row_idx: int, max_col: int) -> list[object]:
    return [ws.cell(row_idx, col).value for col in range(1, max_col + 1)]


def _sheet_looks_like_nds(ws: Worksheet) -> tuple[int, dict[str, int]] | None:
    max_col = min(int(ws.max_column or 0), 20)
    max_row = min(int(ws.max_row or 0), 8)
    if max_col < 5 or max_row < 1:
        return None
    for row_idx in range(1, max_row + 1):
        values = _row_values(ws, row_idx, max_col)
        blob = " ".join(_cell_text(v) for v in values if v is not None)
        if not all(marker in blob for marker in _HEADER_MARKERS):
            continue
        mapping = _header_map(values)
        required = {"buyer_inn", "supplier_inn", "amount", "document_date"}
        if required.issubset(mapping):
            return row_idx, mapping
    return None


def looks_like_nds_request(content: bytes) -> bool:
    try:
        workbook = load_workbook(BytesIO(content), data_only=True, read_only=True)
    except Exception:
        return False
    try:
        for ws in workbook.worksheets:
            if _sheet_looks_like_nds(ws) is not None:
                return True
        return False
    finally:
        workbook.close()


def parse_nds_request_workbook(content: bytes) -> NdsRequestParseResult:
    try:
        workbook = load_workbook(BytesIO(content), data_only=True)
    except Exception as exc:
        return NdsRequestParseResult(matched=False, reason=f"excel_open_failed: {exc}")

    for ws in workbook.worksheets:
        found = _sheet_looks_like_nds(ws)
        if found is None:
            continue
        header_row, cols = found
        lines: list[ParsedApplicationLine] = []
        buyer_inn: str | None = None
        max_row = int(ws.max_row or 0)
        for row_idx in range(header_row + 1, max_row + 1):
            supplier_inn = normalize_inn(ws.cell(row_idx, cols["supplier_inn"]).value)
            row_buyer = normalize_inn(ws.cell(row_idx, cols["buyer_inn"]).value)
            document_date = parse_excel_date(ws.cell(row_idx, cols["document_date"]).value)
            amount = parse_decimal(ws.cell(row_idx, cols["amount"]).value)

            if supplier_inn is None and row_buyer is None and amount is None:
                if lines:
                    # Trailing empty block — stop.
                    empty_ahead = True
                    for peek in range(row_idx + 1, min(row_idx + 3, max_row + 1)):
                        if normalize_inn(ws.cell(peek, cols["supplier_inn"]).value):
                            empty_ahead = False
                            break
                    if empty_ahead:
                        break
                continue
            if supplier_inn is None or document_date is None or amount is None or amount <= 0:
                continue
            if row_buyer:
                buyer_inn = row_buyer
            if buyer_inn is None:
                continue
            lines.append(
                ParsedApplicationLine(
                    supplier_inn=supplier_inn,
                    buyer_inn=buyer_inn,
                    document_date=document_date,
                    amount=amount,
                ),
            )

        if not lines:
            return NdsRequestParseResult(
                matched=True,
                sheet_name=ws.title,
                reason="no_data_rows",
            )
        assert buyer_inn is not None
        return NdsRequestParseResult(
            matched=True,
            sheet_name=ws.title,
            application=ParsedApplication(buyer_inn=buyer_inn, lines=lines),
        )

    return NdsRequestParseResult(matched=False, reason="header_not_found")


class _PriceLine:
    __slots__ = ("supplier_inn", "amount")

    def __init__(self, supplier_inn: str, amount: Decimal) -> None:
        self.supplier_inn = supplier_inn
        self.amount = amount


def lines_for_pricing(application: ParsedApplication) -> list[Any]:
    return [_PriceLine(line.supplier_inn, line.amount) for line in application.lines]
