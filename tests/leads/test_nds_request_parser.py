from __future__ import annotations

from datetime import date
from io import BytesIO
from pathlib import Path

from openpyxl import Workbook

from app.modules.leads.opt.nds_request_parser import (
    looks_like_nds_request,
    parse_nds_request_workbook,
)


def test_parse_sample_nds_request_file() -> None:
    path = Path(__file__).resolve().parents[1] / "63. ЗАПРОС НДС 2 КВ. 2026Г..xlsx"
    if not path.exists():
        # Sample workbook may be absent in CI — skip lightly.
        return
    content = path.read_bytes()
    assert looks_like_nds_request(content)
    result = parse_nds_request_workbook(content)
    assert result.matched
    assert result.form_kind == "nds_request"
    assert result.application is not None
    assert result.application.buyer_inn == "6321443710"
    assert len(result.application.lines) >= 40
    assert result.application.lines[0].supplier_inn == "9704271074"
    assert result.application.lines[0].amount > 0


def test_parse_partner_forma_zayavki_headers() -> None:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Лист_1"
    ws.append(
        [
            "Ваши контактные данные",
            "Наименование покупателя",
            "ИНН покупателя",
            "КПП покупателя",
            "Вид товара",
            "Дата (дд.мм.гг)",
            "Сумма (в т.ч. НДС)",
            "Сумма НДС",
            "ИНН организации",
            "Ставка НДС",
        ],
    )
    ws.append(
        [
            "tg",
            "ООО Тест",
            "7701234567",
            "770101001",
            "услуги",
            date(2026, 4, 15),
            1_000_000,
            166_666.67,
            "9704271074",
            20,
        ],
    )
    buf = BytesIO()
    wb.save(buf)
    content = buf.getvalue()

    assert looks_like_nds_request(content)
    result = parse_nds_request_workbook(content)
    assert result.matched
    assert result.form_kind == "partner_forma"
    assert result.application is not None
    assert result.application.buyer_inn == "7701234567"
    assert len(result.application.lines) == 1
    assert result.application.lines[0].supplier_inn == "9704271074"
    assert result.application.lines[0].amount == 1_000_000


def test_reject_crm_registry_headers() -> None:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "TDSheet"
    ws.append(
        [
            "№ документа",
            "Дата документа",
            "Покупатель",
            "ИНН покупателя",
            "Поставщик",
            "ИНН поставщика",
            "Сумма",
            "Сумма НДС",
            "Сумма без НДС",
        ],
    )
    ws.append(["1", date(2026, 4, 1), "ООО", "7701234567", "ООО2", "9704271074", 100, 20, 80])
    buf = BytesIO()
    wb.save(buf)
    content = buf.getvalue()
    result = parse_nds_request_workbook(content)
    assert result.matched is False


def test_reject_random_bytes() -> None:
    assert not looks_like_nds_request(b"not-an-excel")
    result = parse_nds_request_workbook(b"not-an-excel")
    assert result.matched is False
