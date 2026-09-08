from decimal import Decimal as D
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError
from app.modules.leads.opt.allocation import allocate_amount
from app.modules.leads.opt.schemas import OptSupplierSettlementRequest
from app.modules.leads.opt.service import OptOrderService
from app.shared.exceptions import NotFound


@pytest.mark.parametrize('total,weights', [('1.00', ['1'] * 31), ('0.01', ['1'] * 100), ('100.00', ['0', '0']), ('5.03', ['1', '2', '3'])])
def test_allocation_conserves_money(total, weights):
    result = allocate_amount(D(total), list(map(D, weights)))
    assert sum(result) == D(total)
    assert all(value >= 0 for value in result)


@pytest.mark.parametrize('rate,paid', [(101, 0), (-1, 0), (1, -1), ('NaN', 0), (1, 'NaN')])
def test_invalid_settlement_is_rejected(rate, paid):
    with pytest.raises(ValidationError):
        OptSupplierSettlementRequest(beneficiary_rate_percent=rate, beneficiary_paid_amount=paid)


async def test_saving_checks_order_access_before_reading_or_writing_lines():
    session = AsyncMock()
    service = OptOrderService(session)
    service._get_order_for_actor = AsyncMock(side_effect=NotFound())
    with pytest.raises(NotFound):
        await service.save_supplier_settlement(SimpleNamespace(id=10), 1, 2, '1111111111', OptSupplierSettlementRequest(beneficiary_paid_amount=0))
    session.execute.assert_not_awaited()
    session.flush.assert_not_awaited()


async def test_supplier_settlement_persists_only_selected_shop_and_replaces_total():
    from datetime import date
    from sqlalchemy import insert, select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.orm import raiseload
    import app.modules.db.models  # noqa: F401
    from app.modules.db.models.lead_opt_order import LeadOptOrderLine

    engine = create_async_engine('sqlite+aiosqlite://')
    try:
        async with engine.begin() as connection:
            await connection.run_sync(LeadOptOrderLine.__table__.create)
            for identity, order_id, inn, amount in [(1, 2, '1111111111', 100), (2, 2, '1111111111', 200), (3, 2, '2222222222', 100), (4, 3, '1111111111', 100)]:
                await connection.execute(insert(LeadOptOrderLine).values(
                    id=identity, order_id=order_id, crm_id=str(identity), line_no=identity,
                    supplier_inn=inn, document_date=date(2026, 3, 5), amount=amount,
                    vat_amount=0, amount_without_vat=amount, beneficiary_paid_amount=7,
                ))
        factory = async_sessionmaker(engine)
        async with factory() as session:
            service = OptOrderService(session)
            service._get_order_for_actor = AsyncMock()
            body = OptSupplierSettlementRequest(beneficiary_rate_percent='0.50', beneficiary_paid_amount='10.01', comment=' Договорились ')
            await service.save_supplier_settlement(SimpleNamespace(id=10), 1, 2, '1111111111', body)
            # Re-saving the displayed total must never add the money twice.
            await service.save_supplier_settlement(SimpleNamespace(id=10), 1, 2, '1111111111', body)
            await session.commit()
        async with factory() as session:
            lines = (await session.execute(select(LeadOptOrderLine).options(raiseload('*')).order_by(LeadOptOrderLine.id))).scalars().all()
            assert sum(line.beneficiary_paid_amount for line in lines[:2]) == D('10.01')
            assert all(line.beneficiary_rate_percent == D('0.50') and line.comment == 'Договорились' for line in lines[:2])
            assert all(line.beneficiary_paid_amount == D('7') and line.beneficiary_rate_percent is None for line in lines[2:])
    finally:
        await engine.dispose()
