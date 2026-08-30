from __future__ import annotations

from decimal import Decimal

from app.modules.leads.opt.pricing import (
    commission_base_from_breakdown,
    compute_order_pricing,
    payment_status,
    round_rubles,
)
from app.modules.leads.opt.tariffs import OPT_CATEGORY_TECH


class _Line:
    supplier_inn = "7703822568"
    amount = Decimal("314752")


class _Unit:
    category_code = OPT_CATEGORY_TECH


def test_round_rubles() -> None:
    assert round_rubles("4091.78") == Decimal("4092")
    assert round_rubles("4091.49") == Decimal("4091")


def test_compute_order_pricing_technical_rate() -> None:
    total, commission, breakdown = compute_order_pricing([_Line()], {_Line.supplier_inn: _Unit()})
    assert total == Decimal("314752")
    # 314752 * 1.3% = 4091.776 → whole rubles
    assert commission == Decimal("4092")
    assert breakdown[OPT_CATEGORY_TECH]["rate_percent"] == 1.3
    assert breakdown[OPT_CATEGORY_TECH]["commission"] == 4092.0


def test_payment_status_partial_and_paid() -> None:
    assert payment_status(Decimal("0"), Decimal("100")) == "unpaid"
    assert payment_status(Decimal("40"), Decimal("100")) == "partial"
    assert payment_status(Decimal("100"), Decimal("100")) == "paid"
    assert payment_status(Decimal("0"), Decimal("0")) == "paid"
    assert payment_status(Decimal("0"), Decimal("0"), order_kind="benik") == "unpaid"
    assert payment_status(Decimal("50"), Decimal("100"), order_kind="benik") == "partial"
    assert payment_status(Decimal("100"), Decimal("100"), order_kind="benik") == "paid"


def test_payment_status_kopeck_tail_is_paid() -> None:
    assert payment_status(Decimal("117000"), Decimal("117000.47")) == "paid"
    assert payment_status(Decimal("99.01"), Decimal("100")) == "paid"
    assert payment_status(Decimal("99"), Decimal("100")) == "partial"


def test_rate_percent_for_unit_prefers_custom_rate() -> None:
    from types import SimpleNamespace

    from app.modules.leads.opt.tariffs import OPT_CATEGORY_TECH, rate_percent_for_unit

    unit = SimpleNamespace(commission_rate_percent=1.1, category_code=OPT_CATEGORY_TECH)
    assert rate_percent_for_unit(unit, category_code=OPT_CATEGORY_TECH) == Decimal("1.1")
    assert rate_percent_for_unit(None, category_code=OPT_CATEGORY_TECH) == Decimal("1.3")


def test_mixed_custom_rates_same_category_not_collapsed() -> None:
    """Кохер @2.8% must not inherit 3.5% from another Абсолют (L) supplier."""
    from types import SimpleNamespace

    from app.modules.leads.opt.tariffs import OPT_CATEGORY_ELITE

    class Line:
        def __init__(self, inn: str, amount: str) -> None:
            self.supplier_inn = inn
            self.amount = Decimal(amount)

    units = {
        "7718139114": SimpleNamespace(category_code=OPT_CATEGORY_ELITE, commission_rate_percent=3.5),
        "7734474261": SimpleNamespace(category_code=OPT_CATEGORY_ELITE, commission_rate_percent=2.8),
        "9729097741": SimpleNamespace(category_code=OPT_CATEGORY_ELITE, commission_rate_percent=3.5),
    }
    lines = [
        Line("7718139114", "100000"),
        Line("7734474261", "200000"),
        Line("9729097741", "100000"),
    ]
    total, commission, breakdown = compute_order_pricing(lines, units)  # type: ignore[arg-type]
    assert total == Decimal("400000")
    # 100k*3.5% + 200k*2.8% + 100k*3.5% = 3500 + 5600 + 3500 = 12600
    assert commission == Decimal("12600")
    assert any(abs(float(row["rate_percent"]) - 2.8) < 0.001 for row in breakdown.values())
    assert any(abs(float(row["rate_percent"]) - 3.5) < 0.001 for row in breakdown.values())


def test_commission_base_from_breakdown() -> None:
    breakdown = {
        "TECH": {
            "label": "Техника",
            "volume": 100.0,
            "rate_percent": 1.3,
            "commission": 4091.78,
        }
    }
    assert commission_base_from_breakdown(breakdown) == Decimal("4092")
