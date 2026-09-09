from datetime import date

import pytest

from app.modules.accounting.service import AccountingService
from app.modules.leads.opt.period_access import normalize_requested_period
from app.modules.leads.opt.periods import resolve_application_period
from app.shared.exceptions import ValidationError


@pytest.mark.parametrize("code,year,quarter", [
    ("3/23", 2023, 3), ("4/23", 2023, 4),
    ("1/24", 2024, 1), ("2/24", 2024, 2), ("3/24", 2024, 3), ("4/24", 2024, 4),
])
def test_historical_periods_can_be_assigned_and_used_in_orders(code, year, quarter):
    assert AccountingService(None)._normalize_period_codes([code]) == [code]
    assert normalize_requested_period(code) == code
    result = resolve_application_period([date(year, (quarter - 1) * 3 + 1, 1)], requested_period=code)
    assert result.period_code == code


@pytest.mark.parametrize("code,day", [("1/23", date(2023, 1, 1)), ("2/23", date(2023, 6, 30))])
def test_earlier_quarters_remain_unavailable(code, day):
    with pytest.raises(ValidationError):
        normalize_requested_period(code)
    with pytest.raises(ValidationError):
        resolve_application_period([day])
