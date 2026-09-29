from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from app.modules.users import user_deletion_service as mod
from app.modules.db.models.enums import UserRole, UserStatus
from app.shared.exceptions import PermissionDenied, ValidationError, Conflict

@pytest.mark.asyncio
@pytest.mark.parametrize('role',[r for r in UserRole if r != UserRole.ADMIN])
async def test_admin_can_disable_staff_of_every_role(monkeypatch,role):
    actor=SimpleNamespace(id=1,role=UserRole.ADMIN)
    target=SimpleNamespace(id=2,role=role,status=UserStatus.ACTIVE)
    session=SimpleNamespace(get=AsyncMock(return_value=target),refresh=AsyncMock(),execute=AsyncMock())
    service=mod.UserDeletionRequestService(session)
    service._repo=SimpleNamespace(commit=AsyncMock())
    service._auth=SimpleNamespace(revoke_all_refresh_tokens_for_user=AsyncMock())
    rebalance=AsyncMock();cancel=AsyncMock()
    monkeypatch.setattr(mod,'_reassign_owned_cards_evenly',rebalance)
    monkeypatch.setattr(mod,'_cancel_active_transfers_for_user',cancel)
    from app.modules.audit import service as audit
    write=AsyncMock()
    monkeypatch.setattr(audit,'AuditService',lambda s:SimpleNamespace(write=write))
    assert await service.admin_remove_user(actor,2) is target
    assert target.status == UserStatus.DISABLED
    service._auth.revoke_all_refresh_tokens_for_user.assert_awaited_once_with(2)
    rebalance.assert_awaited_once_with(session,target_user_id=2)
    cancel.assert_awaited_once_with(session,2)
    assert session.get.call_args.kwargs['with_for_update'] is True
    assert write.call_args.kwargs['actor_id'] == 1
    assert write.call_args.kwargs['entity_id'] == 2
    service._repo.commit.assert_awaited_once()

@pytest.mark.asyncio
@pytest.mark.parametrize('role',[r for r in UserRole if r != UserRole.ADMIN])
async def test_staff_cannot_directly_disable_users(role):
    session=SimpleNamespace(get=AsyncMock())
    service=mod.UserDeletionRequestService(session)
    with pytest.raises(PermissionDenied):
        await service.admin_remove_user(SimpleNamespace(id=1,role=role),2)
    session.get.assert_not_awaited()

@pytest.mark.asyncio
@pytest.mark.parametrize('target_id,role,error',[(1,UserRole.ADMIN,ValidationError),(2,UserRole.ADMIN,PermissionDenied)])
async def test_self_and_admin_protected(target_id,role,error):
    session=SimpleNamespace(get=AsyncMock(return_value=SimpleNamespace(id=target_id,role=role)))
    service=mod.UserDeletionRequestService(session)
    service._disable_user_and_rebalance=AsyncMock()
    with pytest.raises(error):
        await service.admin_remove_user(SimpleNamespace(id=1,role=UserRole.ADMIN),target_id)
    service._disable_user_and_rebalance.assert_not_awaited()

@pytest.mark.asyncio
async def test_already_disabled_does_not_rebalance(monkeypatch):
    service=mod.UserDeletionRequestService(SimpleNamespace())
    rebalance=AsyncMock();monkeypatch.setattr(mod,'_reassign_owned_cards_evenly',rebalance)
    with pytest.raises(Conflict):
        await service._disable_user_and_rebalance(SimpleNamespace(status=UserStatus.DISABLED))
    rebalance.assert_not_awaited()
