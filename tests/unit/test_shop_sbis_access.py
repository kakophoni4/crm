from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import pytest
from fastapi import Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.modules.accounting.shop_cards import require_sbis_access, reveal_sbis_password, AccountingShopPatch
from app.modules.db.models.enums import UserRole
from app.modules.lawyer_registry.schemas import LawyerShopOut, LawyerShopPatchRequest
from app.shared.exceptions import PermissionDenied

@pytest.mark.asyncio
async def test_password_scope_requires_the_exact_assignment():
    engine=create_async_engine('sqlite+aiosqlite:///:memory:')
    try:
        async with engine.begin() as c:
            await c.execute(text('CREATE TABLE opt_accountant_unit_assignments (id INTEGER, unit_id INTEGER, user_id INTEGER)'))
            await c.execute(text('INSERT INTO opt_accountant_unit_assignments VALUES (1,10,2)'))
        async with async_sessionmaker(engine)() as db:
            await require_sbis_access(db,SimpleNamespace(id=1,role=UserRole.ADMIN),99)
            await require_sbis_access(db,SimpleNamespace(id=2,role=UserRole.ACCOUNTANT),10)
            for role,user_id,unit_id in [(UserRole.ACCOUNTANT,3,10),(UserRole.ACCOUNTANT,2,11),(UserRole.CHIEF_ACCOUNTANT,3,10),(UserRole.LAWYER,2,10)]:
                with pytest.raises(PermissionDenied):
                    await require_sbis_access(db,SimpleNamespace(id=user_id,role=role),unit_id)
            await db.execute(text('DELETE FROM opt_accountant_unit_assignments'))
            with pytest.raises(PermissionDenied):
                await require_sbis_access(db,SimpleNamespace(id=2,role=UserRole.ACCOUNTANT),10)
    finally: await engine.dispose()

def test_password_not_in_regular_schema_and_masked_in_input_repr():
    assert 'sbis_password' not in LawyerShopOut.model_fields
    assert 'sbis_password_encrypted' not in LawyerShopOut.model_fields
    assert 'sbis_password' not in LawyerShopPatchRequest.model_fields
    body=AccountingShopPatch(sbis_password='test-secret-only')
    assert 'test-secret-only' not in repr(body)
    assert body.sbis_password.get_secret_value()=='test-secret-only'

@pytest.mark.asyncio
async def test_reveal_decrypts_only_after_access_check_and_disables_cache():
    db=AsyncMock();db.scalar.return_value=SimpleNamespace(sbis_password_encrypted=b'encrypted')
    response=Response()
    with patch('app.modules.accounting.shop_cards.scoped_unit',AsyncMock(return_value=SimpleNamespace(inn='123'))),patch('app.modules.accounting.shop_cards.decrypt_secret',AsyncMock(return_value='example')) as decrypt:
        result=await reveal_sbis_password(10,response,SimpleNamespace(id=1,role=UserRole.ADMIN),db)
        assert result=={'password':'example'}
        assert response.headers['Cache-Control']=='no-store'
        decrypt.assert_awaited_once_with(db,b'encrypted')
