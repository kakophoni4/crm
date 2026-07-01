from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.modules.leads.opt.service import OptOrderService
from app.modules.leads.opt.vat import split_vat_included


class _Line:
    crm_id = "crm-line-abc"
    line_no = 1
    supplier_inn = "7743622734"
    supplier_kpp = "774301001"
    supplier_name = "СПЕЦАВТОТРАНССЕРВИС ООО"
    document_date = date(2025, 1, 22)
    amount = 314752.0
    vat_amount = 52458.67
    amount_without_vat = 262293.33


class _Order:
    crm_id = "crm-order-xyz"
    buyer_inn = "5507266215"
    buyer_kpp = "550701001"
    buyer_name = "НАВЕЛ КО ООО"
    lines = [_Line()]


def test_build_mole_payload_matches_1c_contract() -> None:
    total, vat, wo_vat = split_vat_included(Decimal("314752"), rate_percent=Decimal("20"))
    line = _Order.lines[0]
    line.amount = float(total)
    line.vat_amount = float(vat)
    line.amount_without_vat = float(wo_vat)

    payload = OptOrderService._build_mole_payload(_Order())  # type: ignore[arg-type]

    assert payload["CRMid"] == "crm-order-xyz"
    assert payload["Покупатель"] == {
        "ИНН": "5507266215",
        "КПП": "550701001",
        "Наименование": "НАВЕЛ КО ООО",
    }
    assert len(payload["Реестр"]) == 1
    row = payload["Реестр"][0]
    assert row["CRMid"] == "crm-line-abc"
    assert "НомерДокумента" not in row
    assert row["Поставщик"]["ИНН"] == "7743622734"
    assert row["ДатаДокумента"] == "2025-01-22"
    assert row["Сумма"] == 314752.0
    assert row["СуммаНДС"] == 52458.67
    assert row["СуммаБезНДС"] == 262293.33


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
