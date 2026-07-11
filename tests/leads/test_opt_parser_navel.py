from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from app.modules.leads.opt.parser import parse_application_workbook


def test_parse_synthetic_workbook_from_spec() -> None:
    sample = Path(__file__).resolve().parents[2] / "scripts" / "fixtures" / "opt-test-crm.xlsx"
    if not sample.exists():
        pytest.skip("test fixture xlsx not generated — run scripts/opt_build_test_zayavka.py")
    parsed = parse_application_workbook(sample.read_bytes())
    assert parsed.buyer_inn == "7700000100"
    assert len(parsed.lines) == 5
    assert sum(line.amount for line in parsed.lines) == Decimal("1629430")
