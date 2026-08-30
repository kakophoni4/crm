from __future__ import annotations

from datetime import date
from decimal import Decimal
from io import BytesIO

from openpyxl import Workbook

from app.modules.leads.opt.service import _parse_opt_or_benik


def _benik_xlsx() -> bytes:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Заявка на НДС"
    ws.append(
        [
            "Наименование покупателя",
            "ИНН покупателя",
            "КПП",
            "Дата счета-фактуры",
            "Стоимость покупки (с учетом НДС)",
            "Ставка НДС",
            "Наименование продавца",
            "ИНН продавца",
        ],
    )
    ws.append(
        [
            "ООО Покупатель",
            "7707083893",
            "770701001",
            date(2026, 4, 10),
            150_000,
            22,
            "ООО Продавец",
            "9715408489",
        ],
    )
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_parse_opt_or_benik_nds_form() -> None:
    parsed, kind = _parse_opt_or_benik(_benik_xlsx())
    assert kind == "benik"
    assert parsed.buyer_inn == "7707083893"
    assert parsed.buyer_name == "ООО Покупатель"
    assert parsed.buyer_kpp == "770701001"
    assert len(parsed.lines) == 1
    assert parsed.lines[0].supplier_inn == "9715408489"
    assert parsed.lines[0].supplier_name == "ООО Продавец"
    assert parsed.lines[0].amount == Decimal("150000")
