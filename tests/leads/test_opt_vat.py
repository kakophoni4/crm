from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from app.modules.leads.opt.parser import parse_application_workbook
from app.modules.leads.opt.vat import split_vat_included


def test_split_vat_included_matches_registry_sample() -> None:
    total, vat, wo_vat = split_vat_included(Decimal("314752"), rate_percent=Decimal("20"))
    assert total == Decimal("314752.00")
    assert vat == Decimal("52458.67")
    assert wo_vat == Decimal("262293.33")


def test_parse_application_workbook_from_sample() -> None:
    sample = Path(__file__).resolve().parents[2] / "Заявка НАВЕЛ КО 1 кв 25  с вайтами.xlsx"
    if not sample.exists():
        pytest.skip("sample application xlsx not in workspace")
    parsed = parse_application_workbook(sample.read_bytes())
    assert len(parsed.lines) >= 1
    assert parsed.buyer_inn
    assert parsed.lines[0].supplier_inn
    assert parsed.lines[0].amount > 0
