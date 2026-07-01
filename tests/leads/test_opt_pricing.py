from __future__ import annotations

from decimal import Decimal

from app.modules.leads.opt.pricing import compute_order_pricing, payment_status
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
