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


import pytest
from unittest.mock import AsyncMock
from app.modules.leads.opt.repository import OptOrderRepository
from app.shared.exceptions import ValidationError


def order_fixture():
    return S(order_kind="standard", lines=[S(id=1, supplier_inn="123", amount=D("100000"),
             pricing_rate_percent=D("2.8"), pricing_category="O")],
             commission_adjustment=50, amount_paid=1000, commission_due=2850)


async def test_explicit_refresh_updates_snapshot_total_and_balance_without_losing_payments():
    repo = OptOrderRepository(AsyncMock())
    repo.get_units_by_inns = AsyncMock(return_value={"123": S(category_code="L", commission_rate_percent=D("3.7"))})
    order = order_fixture()
    await repo.apply_pricing_snapshot(order, refresh_rates=True, expected_rate=D("3.7"))
    assert order.lines[0].pricing_rate_percent == D("3.7")
    assert order.commission_due == 3750
    assert order.commission_adjustment == 50
    assert order.amount_paid == 1000
    assert order.payment_status == "partial"
    assert order.volume_by_category["L"]["rate_percent"] == 3.7
    repo.get_units_by_inns.assert_awaited_once_with(["123"], active_only=False)


async def test_regular_recalculation_keeps_agreed_rate():
    repo = OptOrderRepository(AsyncMock())
    repo.get_units_by_inns = AsyncMock(return_value={"123": S(category_code="L", commission_rate_percent=D("3.7"))})
    order = order_fixture()
    await repo.apply_pricing_snapshot(order)
    assert order.lines[0].pricing_rate_percent == D("2.8")
    assert order.commission_due == 2850


async def test_refresh_rejects_missing_shop_instead_of_inventing_technical_rate():
    repo = OptOrderRepository(AsyncMock())
    repo.get_units_by_inns = AsyncMock(return_value={})
    order = order_fixture()
    with pytest.raises(ValidationError):
        await repo.apply_pricing_snapshot(order, refresh_rates=True)
    assert order.lines[0].pricing_rate_percent == D("2.8")
    assert order.commission_due == 2850


async def test_expected_rate_is_checked_before_mutating_any_lines():
    repo = OptOrderRepository(AsyncMock())
    repo.get_units_by_inns = AsyncMock(return_value={
        "123": S(category_code="L", commission_rate_percent=D("3.7")),
        "456": S(category_code="O", commission_rate_percent=D("2.8")),
    })
    order = order_fixture()
    order.lines.append(S(id=2, supplier_inn="456", amount=D("100000"), pricing_rate_percent=D("2.8"), pricing_category="O"))
    with pytest.raises(ValidationError):
        await repo.apply_pricing_snapshot(order, refresh_rates=True, expected_rate=D("3.7"))
    assert order.lines[0].pricing_rate_percent == D("2.8")
    assert order.commission_due == 2850


def test_park_import_does_not_erase_manual_rate_on_blank_excel_cell(tmp_path):
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location("park_sync", Path(__file__).resolve().parents[2] / "scripts/opt_sync_park_from_xlsx.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    target = tmp_path / "park.sql"
    module.write_sql([{"inn": "1234567890", "name": "Тест", "category_label": "Оптима", "category_code": "O", "commission_rate_percent": None}], target, deactivate_missing=False)
    sql = target.read_text(encoding="utf-8")
    assert "commission_rate_percent = COALESCE(NULL, commission_rate_percent)" in sql
    assert "commission_rate_percent = NULL," not in sql


async def test_inactive_shop_keeps_its_custom_rate_when_first_snapshot_is_built():
    repo = OptOrderRepository(AsyncMock())
    repo.get_units_by_inns = AsyncMock(return_value={"123": S(category_code="TECH", commission_rate_percent=D("1.1"), is_active=False)})
    order = order_fixture()
    order.lines[0].pricing_rate_percent = None
    await repo.apply_pricing_snapshot(order)
    assert order.lines[0].pricing_rate_percent == D("1.1")
    assert order.commission_due == 1150
