from decimal import Decimal as D
from types import SimpleNamespace as S
from app.modules.leads.opt.pricing import compute_order_pricing
from app.modules.leads.opt.register_pricing import register_line_pricing


def test_shop_rate_change_does_not_change_saved_order():
    line = S(id=1, supplier_inn="123", amount=D("10000"), pricing_rate_percent=D("3.2"), pricing_category="technical")
    total, due, _ = compute_order_pricing([line], {"123":S(category_code="technical",commission_rate_percent=D("9"))})
    assert total == D("10000")
    assert due == D("320")


def test_legacy_mixed_rates_do_not_invent_line_rates_or_change_total():
    order = S(commission_due=D("101.01"), volume_by_category={"a":{"rate_percent":1}, "b":{"rate_percent":3.2}})
    lines = [S(id=1,amount=100), S(id=2,amount=200)]
    rates, amounts, estimated = register_line_pricing(order,lines)
    assert estimated
    assert rates == {1:None,2:None}
    assert sum(amounts.values()) == D("101.01")
