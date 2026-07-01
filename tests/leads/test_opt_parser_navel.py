from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from app.modules.leads.opt.parser import parse_application_workbook


def test_parse_navel_workbook_first_application_only() -> None:
    sample = Path(__file__).resolve().parents[2] / "Заявка НАВЕЛ КО 1 кв 25  с вайтами.xlsx"
    if not sample.exists():
        pytest.skip("NAVEL sample xlsx not in workspace")
    parsed = parse_application_workbook(sample.read_bytes())
    assert parsed.buyer_inn == "5507266215"
    assert len(parsed.lines) == 5
    assert sum(line.amount for line in parsed.lines) == Decimal("1629430")
