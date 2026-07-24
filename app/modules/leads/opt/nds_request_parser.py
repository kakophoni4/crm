"""Detect and parse partner «ЗАПРОС НДС» / Forma_zayavki Excel by content.

Two partner layouts (OPT upload format is intentionally NOT handled here):

1) nds_request — sheet «Заявка на НДС»
   ИНН покупателя | Стоимость покупки | ИНН продавца | дата счета-фактуры

2) partner_forma — Forma_zayavki
   ИНН покупателя | Сумма (в т.ч. НДС) | ИНН организации | дата (дд.мм.гг)

CRM registry exports (№ документа / поставщик / сумма без НДС) are rejected.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from io import BytesIO
from typing import Any, Literal

from openpyxl import load_workbook
from openpyxl.worksheet.worksheet import Worksheet

from app.modules.leads.opt.contact_buyer import normalize_inn, parse_decimal, parse_excel_date
from app.modules.leads.opt.parser import ParsedApplication, ParsedApplicationLine

FormKind = Literal["nds_request", "partner_forma"]


@dataclass(frozen=True)
class NdsRequestParseResult:
    matched: bool
    sheet_name: str | None = None
    application: ParsedApplication | None = None
    reason: str | None = None
    form_kind: FormKind | None = None


_NDS_MARKERS = (
    "инн покупателя",
    "стоимость покупки",
    "инн продавца",
)

_PARTNER_FORMA_MARKERS = (
    "инн покупателя",
    "сумма (в т.ч. ндс)",
    "инн организации",
)

_CRM_REGISTRY_MARKERS = (
    "сумма без ндс",
    "№ документа",
)


def _cell_text(value: object) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().lower().split())


def _blob(values: list[object] | tuple[object, ...]) -> str:
    return " ".join(_cell_text(v) for v in values if v is not None)


def _is_crm_registry_blob(blob: str) -> bool:
    return (
        "сумма без ндс" in blob
        and ("№ документа" in blob or "номер документа" in blob)
        and "поставщик" in blob
    )


def _header_map(row_values: list[object]) -> dict[str, int]:
    """Map logical fields → 1-based column index from a header row."""
    mapping: dict[str, int] = {}
    for idx, raw in enumerate(row_values, start=1):
        text = _cell_text(raw)
        if not text:
            continue
        if "инн покупателя" in text:
            mapping["buyer_inn"] = idx
        elif "инн организации" in text:
            mapping["supplier_inn"] = idx
        elif "инн продавца" in text or ("инн" in text and "продав" in text):
            mapping["supplier_inn"] = idx
        elif "стоимость покупки" in text:
            mapping["amount"] = idx
        elif "сумма (в т.ч. ндс)" in text or "сумма в т.ч. ндс" in text:
            mapping["amount"] = idx
        elif text == "сумма ндс" or text.startswith("сумма ндс "):
            # VAT-only column — not purchase amount.
            continue
        elif "дата счета" in text or "дата счёта" in text or "дата счет" in text:
            mapping["document_date"] = idx
        elif (
            text.startswith("дата (дд")
            or text.startswith("дата(дд")
            or text == "дата"
            or text.startswith("дата реализации")
        ):
            # Prefer purchase/invoice date; «Дата Реализации» is a last-resort for partner forms.
            if "document_date" not in mapping or "реализац" not in text:
                mapping["document_date"] = idx
        elif text.startswith("наименование покупателя"):
            mapping["buyer_name"] = idx
        elif "наименование продавца" in text or "наименование организации" in text:
            mapping["supplier_name"] = idx
    return mapping


def _detect_layout(blob: str, mapping: dict[str, int]) -> FormKind | None:
    required = {"buyer_inn", "supplier_inn", "amount", "document_date"}
    if not required.issubset(mapping):
        return None
    if _is_crm_registry_blob(blob):
        return None
    if all(m in blob for m in _NDS_MARKERS):
        return "nds_request"
    # Partner Forma: amount column is «Сумма (в т.ч. НДС)», seller is «ИНН организации».
    if "инн организации" in blob and (
        "сумма (в т.ч. ндс)" in blob or "сумма в т.ч. ндс" in blob
    ):
        return "partner_forma"
    if all(m in blob for m in _PARTNER_FORMA_MARKERS):
        return "partner_forma"
    # Accept near-match with mapped columns (e.g. стоимость / инн продавца wording variants).
    if "инн покупателя" in blob and "инн" in blob and (
        "стоимость" in blob or "сумма (в т.ч" in blob
    ):
        if "инн продавца" in blob:
            return "nds_request"
        if "инн организации" in blob:
            return "partner_forma"
    return None


def _row_values(ws: Worksheet, row_idx: int, max_col: int) -> list[object]:
    return [ws.cell(row_idx, col).value for col in range(1, max_col + 1)]


_HEADER_SCAN_ROWS = 20
_HEADER_SCAN_COLS = 24


def _sheet_looks_like_partner(
    ws: Worksheet,
) -> tuple[int, dict[str, int], FormKind] | None:
    max_col = min(int(ws.max_column or 0), _HEADER_SCAN_COLS)
    max_row = min(int(ws.max_row or 0), _HEADER_SCAN_ROWS)
    if max_col < 4 or max_row < 1:
        return None
    for row_idx in range(1, max_row + 1):
        values = _row_values(ws, row_idx, max_col)
        blob = _blob(values)
        if not blob or _is_crm_registry_blob(blob):
            continue
        mapping = _header_map(values)
        kind = _detect_layout(blob, mapping)
        if kind is not None:
            return row_idx, mapping, kind
    return None


def _quick_has_partner_headers(content: bytes) -> bool:
    """Fast path: only first rows via read_only — avoids loading huge unrelated books."""
    try:
        workbook = load_workbook(BytesIO(content), data_only=True, read_only=True)
    except Exception:
        return False
    try:
        for ws in workbook.worksheets:
            for row in ws.iter_rows(
                min_row=1,
                max_row=_HEADER_SCAN_ROWS,
                max_col=_HEADER_SCAN_COLS,
                values_only=True,
            ):
                blob = _blob(row)
                if not blob or _is_crm_registry_blob(blob):
                    continue
                if all(m in blob for m in _NDS_MARKERS):
                    return True
                if "инн покупателя" in blob and "инн организации" in blob and (
                    "сумма (в т.ч. ндс)" in blob or "сумма в т.ч. ндс" in blob
                ):
                    return True
        return False
    finally:
        workbook.close()


def peek_workbook_headers(content: bytes, *, max_rows: int = 8) -> list[dict[str, object]]:
    """Return first non-empty rows per sheet (for SKIP diagnostics / audit)."""
    if content[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        return [{"sheet": None, "reason": "xls_legacy_not_supported"}]
    try:
        workbook = load_workbook(BytesIO(content), data_only=True, read_only=True)
    except Exception as exc:
        return [{"sheet": None, "reason": f"excel_open_failed: {exc}"}]
    out: list[dict[str, object]] = []
    try:
        for ws in workbook.worksheets:
            for row_idx, row in enumerate(
                ws.iter_rows(
                    min_row=1,
                    max_row=max_rows,
                    max_col=_HEADER_SCAN_COLS,
                    values_only=True,
                ),
                start=1,
            ):
                cells = [str(v).strip() for v in row if v is not None and str(v).strip()]
                if len(cells) < 2:
                    continue
                out.append(
                    {
                        "sheet": ws.title,
                        "row": row_idx,
                        "headers": cells[:16],
                        "blob": _blob(row)[:240],
                    },
                )
                break
    finally:
        workbook.close()
    return out


def looks_like_nds_request(content: bytes) -> bool:
    if content[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        return False
    return _quick_has_partner_headers(content)


def parse_nds_request_workbook(content: bytes) -> NdsRequestParseResult:
    if content[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        return NdsRequestParseResult(
            matched=False,
            reason="xls_legacy_not_supported",
        )
    if not _quick_has_partner_headers(content):
        return NdsRequestParseResult(matched=False, reason="header_not_found")

    try:
        workbook = load_workbook(BytesIO(content), data_only=True)
    except Exception as exc:
        return NdsRequestParseResult(matched=False, reason=f"excel_open_failed: {exc}")

    for ws in workbook.worksheets:
        found = _sheet_looks_like_partner(ws)
        if found is None:
            continue
        header_row, cols, form_kind = found
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
                form_kind=form_kind,
            )
        assert buyer_inn is not None
        return NdsRequestParseResult(
            matched=True,
            sheet_name=ws.title,
            application=ParsedApplication(buyer_inn=buyer_inn, lines=lines),
            form_kind=form_kind,
        )

    return NdsRequestParseResult(matched=False, reason="header_not_found")


class _PriceLine:
    __slots__ = ("supplier_inn", "amount")

    def __init__(self, supplier_inn: str, amount: Decimal) -> None:
        self.supplier_inn = supplier_inn
        self.amount = amount


def lines_for_pricing(application: ParsedApplication) -> list[Any]:
    return [_PriceLine(line.supplier_inn, line.amount) for line in application.lines]
