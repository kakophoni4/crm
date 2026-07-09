from __future__ import annotations

from decimal import Decimal

from app.modules.leads.opt.pricing import (
    commission_base_from_breakdown,
    compute_order_pricing,
    payment_status,
)
from app.modules.leads.opt.tariffs import OPT_CATEGORY_TECH


class _Line:
    supplier_inn = "7703822568"
    amount = Decimal("314752")


class _Unit:
    category_code = OPT_CATEGORY_TECH


def test_compute_order_pricing_technical_rate() -> None:
    total, commission, breakdown = compute_order_pricing([_Line()], {_Line.supplier_inn: _Unit()})
    assert total == Decimal("314752")
    assert commission == Decimal("4091.78")
    assert breakdown[OPT_CATEGORY_TECH]["rate_percent"] == 1.3


def test_payment_status_partial_and_paid() -> None:
    assert payment_status(Decimal("0"), Decimal("100")) == "unpaid"
    assert payment_status(Decimal("40"), Decimal("100")) == "partial"
    assert payment_status(Decimal("100"), Decimal("100")) == "paid"


def test_rate_percent_for_unit_prefers_custom_rate() -> None:
    from types import SimpleNamespace

    from app.modules.leads.opt.tariffs import OPT_CATEGORY_TECH, rate_percent_for_unit

    unit = SimpleNamespace(commission_rate_percent=1.1, category_code=OPT_CATEGORY_TECH)
    assert rate_percent_for_unit(unit, category_code=OPT_CATEGORY_TECH) == Decimal("1.1")
    assert rate_percent_for_unit(None, category_code=OPT_CATEGORY_TECH) == Decimal("1.3")


def test_commission_base_from_breakdown() -> None:
    breakdown = {
        "TECH": {
            "label": "Техника",
            "volume": 100.0,
            "rate_percent": 1.3,
            "commission": 4091.78,
        }
    }
    assert commission_base_from_breakdown(breakdown) == Decimal("4091.78")
