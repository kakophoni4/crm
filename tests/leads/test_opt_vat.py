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


def test_parse_test_fixture_workbook() -> None:
    root = Path(__file__).resolve().parents[2]
    sample = root / "scripts" / "fixtures" / "opt-test-crm.xlsx"
    if not sample.exists():
        sample = root / "scripts" / "fixtures" / "Заявка-тест-CRM.xlsx"
    if not sample.exists():
        pytest.skip("test fixture xlsx not generated — run scripts/opt_build_test_zayavka.py")
    parsed = parse_application_workbook(sample.read_bytes())
    assert parsed.buyer_inn == "5507266215"
    assert len(parsed.lines) == 5
    assert parsed.lines[0].supplier_inn == "7703822568"
    assert str(parsed.lines[0].document_date) == "2025-01-22"
    assert parsed.lines[0].amount == Decimal("314752")
