from __future__ import annotations

from datetime import date

import pytest

from app.modules.leads.opt.periods import (
    period_code_from_date,
    resolve_application_period,
)
from app.shared.exceptions import ValidationError


def test_period_code_from_date() -> None:
    assert period_code_from_date(date(2025, 12, 31)) == "4/25"
    assert period_code_from_date(date(2026, 1, 1)) == "1/26"
    assert period_code_from_date(date(2026, 4, 15)) == "2/26"


def test_resolve_application_period_majority() -> None:
    dates = [
        date(2026, 4, 1),
        date(2026, 5, 10),
        date(2026, 6, 20),
    ]
    resolved = resolve_application_period(dates)
    assert resolved.period_code == "2/26"


def test_resolve_application_period_rejects_outliers() -> None:
    dates = [
        date(2026, 4, 1),
        date(2026, 5, 10),
        date(2026, 5, 11),
        date(2026, 1, 15),
    ]
    with pytest.raises(ValidationError, match="другого квартала") as exc:
        resolve_application_period(dates)
    assert "15.01.2026" in exc.value.message
    assert "1 кв. 2026" in exc.value.message


def test_resolve_application_period_rejects_tie() -> None:
    dates = [date(2026, 3, 31), date(2026, 4, 1)]
    with pytest.raises(ValidationError, match="поровну"):
        resolve_application_period(dates)


def test_resolve_application_period_rejects_selected_mismatch() -> None:
    dates = [date(2025, 11, 1), date(2025, 12, 2)]
    with pytest.raises(ValidationError, match="4 кв. 2025") as exc:
        resolve_application_period(dates, requested_period="2/26")
    assert "2 кв. 2026" in exc.value.message


def test_resolve_application_period_accepts_matching_selected() -> None:
    dates = [date(2026, 7, 1), date(2026, 8, 2)]
    resolved = resolve_application_period(dates, requested_period="3/26")
    assert resolved.period_code == "3/26"
