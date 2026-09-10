from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.modules.cashroom.router import (
    DealBody, MovementBody, VoidBody, calculate, create_deal, update_deal,
    create_movement, void_movement, deals, accounts, suggestions, detail,
)
from app.modules.db.models.cashroom import CashAccount, CashDeal, CashMovement, CashAudit
from app.modules.db.models.enums import UserRole
from app.modules.rbac.permissions import Permission
from app.modules.rbac.role_map import ROLE_PERMISSIONS
from app.shared.exceptions import Conflict


def test_excel_calculation_and_rounding():
    result = calculate(300000, 20, 22, 1, 240000, 234000)
    assert result['profit'] == Decimal('3000.00')
    assert result['salary'] == Decimal('3000.00')
    assert result['receivable'] == result['payable'] == 0
    assert calculate('0.05', 50, 0, 0)['expected_received'] == Decimal('0.03')
    assert calculate(100, 0, 0, 0, 110)['receivable'] == -10


def test_role_is_restricted():
    assert Permission.CASHROOM_MANAGE in ROLE_PERMISSIONS[UserRole.ADMIN]
    assert Permission.CASHROOM_MANAGE in ROLE_PERMISSIONS[UserRole.KESHER]
    assert all(p.value.startswith('profile.') or p == Permission.CASHROOM_MANAGE
               for p in ROLE_PERMISSIONS[UserRole.KESHER])
    assert Permission.CASHROOM_MANAGE not in ROLE_PERMISSIONS[UserRole.USER]


@pytest.mark.asyncio
async def test_payment_retry_void_filters_and_edit_conflict():
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    try:
        async with engine.begin() as conn:
            await conn.execute(text('CREATE TABLE users (id BIGINT PRIMARY KEY, full_name TEXT)'))
            await conn.execute(text("INSERT INTO users VALUES (1, 'Кешер')"))
            for model in (CashAccount, CashDeal, CashMovement, CashAudit):
                await conn.run_sync(lambda c, t=model.__table__: t.create(c))
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            actor = SimpleNamespace(id=1)
            account = CashAccount(name='Касса 1')
            db.add(account)
            await db.commit()
            body = DealBody(entered_on=date.today(), due_on=date.today()-timedelta(days=1),
                            payer='Плательщик', receiver='Получатель', client='Клиент',
                            executor='Исполнитель', amount=300000, executor_rate=20,
                            client_rate=22, manager_rate=1)
            deal_id = (await create_deal(body, db, actor))['id']
            assert await suggestions(db, actor, field='client', q='Кли') == ['Клиент']
            payment = MovementBody(operation_key=uuid4(), account_id=account.id,
                                   deal_id=deal_id, kind='receive', amount=240000,
                                   occurred_on=date.today())
            first = await create_movement(payment, db, actor)
            assert await create_movement(payment, db, actor) == first
            with pytest.raises(Conflict):
                await create_movement(payment.model_copy(update={'amount': Decimal('1')}), db, actor)
            result = await deals(db, actor, state='partial', page=1, page_size=30)
            assert result['summary']['count'] == 1
            assert result['items'][0]['received'] == '240000.00'
            assert (await accounts(db, actor))[0]['balance'] == '240000.00'
            await void_movement(first['id'], VoidBody(reason='Ошибка суммы'), db, actor)
            assert (await accounts(db, actor))[0]['balance'] == '0.00'
            history = await detail(deal_id, db, actor)
            assert history['movements'][0]['voided'] is True
            assert history['history'][0]['action'] == 'payment_voided'
            result = await deals(db, actor, state='overdue', page=1, page_size=30)
            assert result['summary']['count'] == 1
            assert result['items'][0]['receivable'] == '240000.00'
            assert (await deals(db, actor, q='несуществующий', page=1, page_size=30))['summary']['count'] == 0
            await update_deal(deal_id, body.model_copy(update={'client':'Другой'}), db, actor)
            with pytest.raises(Conflict):
                await update_deal(deal_id, body, db, actor)
    finally:
        await engine.dispose()
