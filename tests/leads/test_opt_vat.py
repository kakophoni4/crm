from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from app.modules.leads.opt.parser import parse_application_workbook
from app.modules.leads.opt.vat import (
    normalize_opt_vat_rate,
    split_vat_included,
    vat_rate_for_period_code,
)


def test_vat_rate_switches_at_q1_2026() -> None:
    assert vat_rate_for_period_code("4/25") == Decimal("20")
    assert vat_rate_for_period_code("1/25") == Decimal("20")
    assert vat_rate_for_period_code("1/26") == Decimal("22")
    assert vat_rate_for_period_code("2/26") == Decimal("22")


def test_normalize_opt_vat_rate_accepts_strings() -> None:
    assert normalize_opt_vat_rate("20") == Decimal("20")
    assert normalize_opt_vat_rate("22") == Decimal("22")
    assert normalize_opt_vat_rate(20) == Decimal("20")


def test_split_vat_included_matches_registry_sample() -> None:
    total, vat, wo_vat = split_vat_included(Decimal("314752"), rate_percent=Decimal("22"))
    assert total == Decimal("314752.00")
    assert vat == Decimal("56758.56")
    assert wo_vat == Decimal("257993.44")


def test_parse_test_fixture_workbook() -> None:
    root = Path(__file__).resolve().parents[2]
    sample = root / "scripts" / "fixtures" / "opt-test-crm.xlsx"
    if not sample.exists():
        pytest.skip("test fixture xlsx not generated — run scripts/opt_build_test_zayavka.py")
    parsed = parse_application_workbook(sample.read_bytes())
    assert parsed.buyer_inn == "7700000100"
    assert len(parsed.lines) == 5
    assert parsed.lines[0].supplier_inn == "7700000001"
    assert str(parsed.lines[0].document_date) == "2025-01-22"
    assert parsed.lines[0].amount == Decimal("314752")
    assert parsed.lines[1].amount == Decimal("342500")
    assert parsed.lines[4].supplier_inn == "7700000003"
    assert parsed.lines[4].amount == Decimal("395671")
