from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from io import BytesIO

from openpyxl import load_workbook

from app.modules.leads.opt.contact_buyer import normalize_inn, parse_decimal, parse_excel_date
from app.shared.exceptions import ValidationError


@dataclass(frozen=True)
class ParsedApplicationLine:
    supplier_inn: str
    buyer_inn: str
    document_date: date
    amount: Decimal


@dataclass(frozen=True)
class ParsedApplication:
    buyer_inn: str
    lines: list[ParsedApplicationLine]


def parse_application_workbook(content: bytes) -> ParsedApplication:
    try:
        workbook = load_workbook(BytesIO(content), data_only=True)
    except Exception as exc:
        raise ValidationError(message="Не удалось прочитать Excel-файл заявки") from exc

    worksheet = workbook.active
    lines: list[ParsedApplicationLine] = []
    buyer_inn: str | None = None

    for row_idx in range(4, (worksheet.max_row or 0) + 1):
        supplier_inn = normalize_inn(worksheet.cell(row_idx, 2).value)
        row_buyer_inn = normalize_inn(worksheet.cell(row_idx, 3).value)
        document_date = parse_excel_date(worksheet.cell(row_idx, 4).value)
        amount = parse_decimal(worksheet.cell(row_idx, 5).value)

        if supplier_inn is None and row_buyer_inn is None:
            if lines:
                break
            continue
        if supplier_inn is None or document_date is None or amount is None or amount <= 0:
            if lines:
                break
            continue

        if row_buyer_inn:
            buyer_inn = row_buyer_inn
        elif buyer_inn is None:
            raise ValidationError(message="В заявке не найден ИНН покупателя")

        lines.append(
            ParsedApplicationLine(
                supplier_inn=supplier_inn,
                buyer_inn=buyer_inn or row_buyer_inn or "",
                document_date=document_date,
                amount=amount,
            ),
        )

    if not lines:
        raise ValidationError(message="В файле заявки не найдено строк с операциями")
    if buyer_inn is None:
        buyer_inn = lines[0].buyer_inn
    if not buyer_inn:
        raise ValidationError(message="ИНН покупателя обязателен")

    return ParsedApplication(buyer_inn=buyer_inn, lines=lines)
