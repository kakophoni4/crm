"""Standalone regression suite: pytest --confcutdir=tests/workspace_regression."""
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

import app.modules.db.models  # noqa: F401: register FK targets
from app.modules.db.models.lawyer_director import LawyerShop, LawyerDirector
from app.modules.db.models.opt_unit import OptUnit
from app.modules.db.models.opt_accountant_unit_assignment import OptAccountantUnitAssignment
from app.modules.db.models.enums import UserRole
from app.modules.lawyer_registry.router import router
from app.shared.db import get_db
from app.shared.security.deps import current_user
from app.shared.exceptions import register_exception_handlers


@pytest.fixture
async def api():
    engine = create_async_engine('sqlite+aiosqlite://')
    async with engine.begin() as connection:
        for model in [LawyerDirector, LawyerShop, OptUnit, OptAccountantUnitAssignment]:
            await connection.run_sync(model.__table__.create)
        await connection.execute(insert(LawyerDirector).values(id=1, full_name='Общий директор', name_key='shared', passport='SECRET'))
        await connection.execute(insert(LawyerDirector).values(id=2, full_name='Чужой директор', name_key='foreign'))
        for i, director in [(1, 1), (2, 1), (3, 2)]:
            await connection.execute(insert(LawyerShop).values(id=i, inn=str(i) * 10, name=f'Лавка {i}', director_id=director, kind='priority', source='manual'))
            await connection.execute(insert(OptUnit).values(id=i, inn=str(i) * 10, name=f'Лавка {i}'))
        await connection.execute(insert(OptAccountantUnitAssignment).values(id=1, user_id=10, unit_id=1))
        await connection.execute(insert(OptAccountantUnitAssignment).values(id=2, user_id=20, unit_id=2))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    actor = SimpleNamespace(id=10, role=UserRole.ACCOUNTANT)
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)
    from app.modules.accounting.shop_cards import router as cards_router
    app.include_router(cards_router)
    async def session_override():
        async with factory() as session:
            yield session
    app.dependency_overrides[get_db] = session_override
    app.dependency_overrides[current_user] = lambda: actor
    async with AsyncClient(transport=ASGITransport(app), base_url='http://test') as client:
        yield client, actor
    await engine.dispose()


@pytest.mark.parametrize('role', [UserRole.ACCOUNTANT, UserRole.CHIEF_ACCOUNTANT])
async def test_only_assigned_shops_and_no_director_private_data(api, role):
    client, actor = api
    actor.role = role
    response = await client.get('/api/v1/lawyer-registry')
    assert response.status_code == 200
    data = response.json()
    assert data['total_shops'] == 1
    assert [shop['id'] for d in data['items'] for shop in d['shops']] == [1]
    assert data['pinned_shops'] == []
    assert data['items'][0]['passport'] is None
    assert data['items'][0]['payments'] == []
    detail = (await client.get('/api/v1/lawyer-registry/directors/1')).json()
    assert [shop['id'] for shop in detail['shops']] == [1]
    assert (await client.get('/api/v1/lawyer-registry/directors/2')).status_code == 404
    assert (await client.get('/api/v1/lawyer-registry?q=2222222222')).json()['total_shops'] == 0


async def test_no_assignments_and_mutations_denied(api):
    client, actor = api
    actor.id = 999
    data = (await client.get('/api/v1/lawyer-registry')).json()
    assert data['items'] == [] and data['orphan_shops'] == []
    assert (await client.get('/api/v1/lawyer-registry/alerts')).json() == {'items': [], 'unread': 0}
    assert (await client.patch('/api/v1/lawyer-registry/shops/1', json={'name': 'Changed'})).status_code == 403
    assert (await client.post('/api/v1/lawyer-registry/alerts/read', json={})).status_code == 403


async def test_accountant_edits_shared_card_and_clears_values(api):
    client, actor = api
    response = await client.patch('/api/v1/accounting/units/1/card', json={'name': 'Новое имя', 'fns': '1234', 'edo_until': '2027-12-31', 'received_at': '2026-09-08', 'dirovod': 'Ответственный'})
    assert response.status_code == 200, response.text
    assert response.json()['fns'] == '1234'
    assert response.json()['received_at'] == '2026-09-08'
    assert response.json()['dirovod'] == 'Ответственный'
    shared = (await client.get('/api/v1/lawyer-registry/directors/1')).json()['shops'][0]
    assert shared['name'] == 'Новое имя' and shared['edo_until'] == '2027-12-31'
    response = await client.patch('/api/v1/accounting/units/1/card', json={'fns': None})
    assert response.status_code == 200 and response.json()['fns'] is None
    assert response.json()['edo_until'] == '2027-12-31'


async def test_accountant_cannot_read_or_write_foreign_card(api):
    client, actor = api
    for unit_id in (2, 3, 999):
        assert (await client.get(f'/api/v1/accounting/units/{unit_id}/card')).status_code == 404
        assert (await client.patch(f'/api/v1/accounting/units/{unit_id}/card', json={'fns': 'bad'})).status_code == 404
    assert (await client.patch('/api/v1/accounting/units/1/card', json={'accountant': 'Other'})).status_code == 422


async def test_chief_can_edit_all_shop_cards(api):
    client, actor = api
    actor.role = UserRole.CHIEF_ACCOUNTANT
    response = await client.patch('/api/v1/accounting/units/2/card', json={'sbis': 'Активен'})
    assert response.status_code == 200, response.text
    assert response.json()['sbis'] == 'Активен'
