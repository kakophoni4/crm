from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.modules.leads.opt.mole_client import _normalize_mole_status
from app.modules.leads.opt.service import OptOrderService
from app.modules.leads.opt.vat import split_vat_included


class _Line:
    crm_id = "crm-line-abc"
    line_no = 1
    supplier_inn = "7700000001"
    supplier_kpp = "770001001"
    supplier_name = 'ООО "Тестовая лавка 1"'
    document_date = date(2025, 1, 22)
    amount = 314752.0
    vat_amount = 52458.67
    amount_without_vat = 262293.33


class _Order:
    crm_id = "crm-order-xyz"
    buyer_inn = "7700000100"
    buyer_kpp = "770001001"
    buyer_name = 'ООО "Тестовый покупатель"'
    lines = [_Line()]


def test_build_mole_payload_matches_1c_contract() -> None:
    total, vat, wo_vat = split_vat_included(Decimal("314752"), rate_percent=Decimal("22"))
    line = _Order.lines[0]
    line.amount = float(total)
    line.vat_amount = float(vat)
    line.amount_without_vat = float(wo_vat)

    payload = OptOrderService._build_mole_payload(_Order())  # type: ignore[arg-type]

    assert payload["CRMid"] == "crm-order-xyz"
    assert payload["Покупатель"] == {
        "ИНН": "7700000100",
        "КПП": "770001001",
        "Наименование": 'ООО "Тестовый покупатель"',
    }
    assert len(payload["Реестр"]) == 1
    row = payload["Реестр"][0]
    assert row["CRMid"] == "crm-line-abc"
    assert "НомерДокумента" not in row
    assert row["Поставщик"]["ИНН"] == "7700000001"
    assert row["ДатаДокумента"] == "2025-01-22"
    assert row["Сумма"] == 314752.0
    assert row["СуммаНДС"] == 56758.56
    assert row["СуммаБезНДС"] == 257993.44


def test_build_mole_payload_sends_empty_kpp_when_missing() -> None:
    order = _Order()
    order.buyer_kpp = None
    order.lines[0].supplier_kpp = None

    payload = OptOrderService._build_mole_payload(order)  # type: ignore[arg-type]

    assert payload["Покупатель"] == {
        "ИНН": "7700000100",
        "КПП": "",
        "Наименование": 'ООО "Тестовый покупатель"',
    }
    assert payload["Реестр"][0]["Поставщик"] == {
        "ИНН": "7700000001",
        "КПП": "",
        "Наименование": 'ООО "Тестовая лавка 1"',
    }


def test_extract_line_numbers_accepts_crmid() -> None:
    mapping = OptOrderService._extract_line_numbers(
        {
            "Статус": "OK",
            "CRMid": "crm-order-xyz",
            "Реестр": [
                {"CRMid": "crm-line-abc", "НомерДокумента": "СА-000000042"},
            ],
        },
    )
    assert mapping == {"crm-line-abc": "СА-000000042"}


def test_normalize_mole_status_accepts_cyrillic_ok() -> None:
    assert _normalize_mole_status("ОК") == "OK"
    assert _normalize_mole_status("ок") == "OK"
    assert _normalize_mole_status("OK") == "OK"
