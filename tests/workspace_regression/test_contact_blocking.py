from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from app.modules.chats import blocking as mod
from app.modules.db.models.enums import BotOutboundStatus
from app.workers.bots.dispatch_outbound import validate_bridge_result, BridgeCommandRejected
from app.shared.exceptions import NotFound, ValidationError


def row(status):
    return SimpleNamespace(status=status, created_at=datetime.now(timezone.utc), payload={'operator': {'name': 'Operator'}, 'reason': 'spam'})


@pytest.mark.parametrize('result', [None, {}, {'status': 'ok'}, {'status': 'ok', 'is_access': True, 'telegram_user_id': 123}, {'status': 'ok', 'is_access': False, 'telegram_user_id': 456}])
def test_false_success_is_rejected(result):
    with pytest.raises(BridgeCommandRejected):
        validate_bridge_result('block_contact', {'contact': {'telegram_user_id': 123}}, result)


def test_idempotent_bridge_success_accepted():
    validate_bridge_result('block_contact', {'contact': {'telegram_user_id': 123}},
        {'status': 'ok', 'is_access': False, 'telegram_user_id': 123, 'changed': False})


def test_blocked_message_is_not_delivered():
    with pytest.raises(BridgeCommandRejected, match='contact_blocked'):
        validate_bridge_result('send_message', {}, {'error_code': 'contact_blocked', 'retryable': False})


@pytest.mark.parametrize('dbstate, expected', [(BotOutboundStatus.QUEUED, 'pending'), (BotOutboundStatus.FAILED, 'failed'), (BotOutboundStatus.SENT, 'blocked')])
def test_only_confirmed_outbox_is_blocked(dbstate, expected):
    assert mod.block_state(row(dbstate))['status'] == expected


@pytest.mark.asyncio
async def test_scope_denial_cannot_queue(monkeypatch):
    monkeypatch.setattr(mod, 'ChatRepository', lambda db: SimpleNamespace(get_by_id=AsyncMock(return_value=SimpleNamespace())))
    monkeypatch.setattr(mod, 'ScopeLoader', lambda db: SimpleNamespace(load=AsyncMock(return_value='scope')))
    monkeypatch.setattr(mod, 'can_view_chat_async', AsyncMock(return_value=False))
    db = SimpleNamespace(get=AsyncMock())
    with pytest.raises(NotFound):
        await mod.request_block(db, 'actor', 1, 'spam')
    db.get.assert_not_awaited()


@pytest.mark.asyncio
async def test_non_telegram_cannot_block(monkeypatch):
    monkeypatch.setattr(mod, 'block_context', AsyncMock(return_value=(None, SimpleNamespace(channel='whatsapp'), None)))
    with pytest.raises(ValidationError):
        await mod.request_block(None, None, 1, '')


@pytest.mark.asyncio
@pytest.mark.parametrize('status', [BotOutboundStatus.QUEUED, BotOutboundStatus.SENT])
async def test_repeated_click_does_not_enqueue(monkeypatch, status):
    monkeypatch.setattr(mod, 'ChatRepository', lambda db: SimpleNamespace(get_active_takeover=AsyncMock(return_value=None)))
    monkeypatch.setattr(mod, 'block_context', AsyncMock(return_value=(SimpleNamespace(), SimpleNamespace(channel='telegram', is_active=True), SimpleNamespace(id=1, telegram_user_id=123))))
    monkeypatch.setattr(mod, 'latest_block', AsyncMock(return_value=row(status)))
    db = SimpleNamespace(scalar=AsyncMock())
    assert (await mod.request_block(db, None, 1, ''))['status'] in ('pending', 'blocked')


@pytest.mark.asyncio
async def test_request_records_audit_and_defers_queue(monkeypatch):
    monkeypatch.setattr(mod, 'ChatRepository', lambda db: SimpleNamespace(get_active_takeover=AsyncMock(return_value=None)))
    bot = SimpleNamespace(id=2, channel='telegram', is_active=True)
    monkeypatch.setattr(mod, 'block_context', AsyncMock(return_value=(SimpleNamespace(id=7), bot, SimpleNamespace(id=1, telegram_user_id=123))))
    monkeypatch.setattr(mod, 'latest_block', AsyncMock(return_value=None))
    saved = row(BotOutboundStatus.QUEUED); saved.id = 99
    create = AsyncMock(return_value=saved)
    monkeypatch.setattr(mod, 'BotOutboundLogRepository', lambda db: SimpleNamespace(create=create))
    audit = AsyncMock()
    monkeypatch.setattr(mod, 'AuditService', lambda db: SimpleNamespace(write=audit))
    hooks=[]
    monkeypatch.setattr(mod, 'schedule_after_commit', lambda db, fn: hooks.append(fn))
    queue = AsyncMock(); monkeypatch.setattr(mod, 'queue_block', queue)
    result=await mod.request_block(SimpleNamespace(scalar=AsyncMock()), SimpleNamespace(id=4, full_name='Operator'), 7, ' spam ')
    assert result['status']=='pending'
    assert create.await_args.kwargs['payload']['contact']=={'telegram_user_id':123}
    assert create.await_args.kwargs['payload']['operator']['id']==4
    assert create.await_args.kwargs['command']=='block_contact'
    audit.assert_awaited_once()
    queue.assert_not_awaited()
    await hooks[0]()
    queue.assert_awaited_once_with(99,2)
