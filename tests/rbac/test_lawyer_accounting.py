from types import SimpleNamespace

import pytest

from app.modules.accounting.service import AccountingService
from app.modules.db.models.enums import UserRole
from app.modules.rbac.permissions import Permission
from app.modules.rbac.role_map import has_permission


def test_lawyer_can_manage_accounting_without_user_administration():
    assert has_permission(UserRole.LAWYER, Permission.ACCOUNTING_READ)
    assert has_permission(UserRole.LAWYER, Permission.ACCOUNTING_MANAGE)
    assert not has_permission(UserRole.LAWYER, Permission.USERS_CREATE)
    assert not has_permission(UserRole.USER, Permission.ACCOUNTING_READ)
    assert not has_permission(UserRole.ACCOUNTANT, Permission.ACCOUNTING_MANAGE)


@pytest.mark.asyncio
async def test_lawyer_sees_all_shops_without_assignments():
    service = AccountingService(None)
    actor = SimpleNamespace(id=123, role=UserRole.LAWYER)
    assert service._is_chief(actor)
    assert await service._visible_supplier_inns(actor) is None
    assert await service._visible_supplier_inns(actor, active_only=False) is None
