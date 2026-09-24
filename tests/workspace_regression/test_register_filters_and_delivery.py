import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from contextlib import asynccontextmanager
import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql
from app.modules.leads.opt.register_query import parse_filters, apply_register_query, KEYS, NUMERIC
from app.modules.db.models.lead_opt_order import LeadOptOrder as Order
from app.modules.db.models.lead import Lead
from app.modules.db.models.contact import Contact
from app.modules.db.models.contact_group_assignment import ContactGroupAssignment as Assignment
from app.shared.exceptions import ValidationError
from app.workers.bots import dispatch_outbound as delivery

@pytest.mark.parametrize('raw', ['[]', '{"unknown":"x"}', '{"paid":{"min":100,"max":1}}', '{"paid":{"min":"NaN"}}', '{"paid":{"min":true}}', '{"client":2}'])
def test_invalid_filters_rejected(raw):
    with pytest.raises(ValidationError): parse_filters(raw)

@pytest.mark.parametrize('key', sorted(KEYS))
def test_global_query_keeps_scope_and_orders_before_pagination(key):
    query = (select(Order.id).join(Lead, Lead.id == Order.lead_id)
        .outerjoin(Contact, Contact.id == Lead.contact_id)
        .outerjoin(Assignment, (Assignment.contact_id == Lead.contact_id) & (Assignment.group_id == Lead.group_id))
        .where(Lead.group_id.in_([17]), Order.deleted_at.is_(None)))
    query, order = apply_register_query(query, json.dumps({key: {'min': 100} if key in NUMERIC else '100%_'}), key, False)
    compiled = query.order_by(order, Order.id.desc()).offset(30).limit(30).compile(dialect=postgresql.dialect())
    sql = str(compiled)
    assert 'leads.group_id IN' in sql and 'deleted_at IS NULL' in sql
    assert sql.index('ORDER BY') < sql.index('LIMIT')
    assert 'ASC NULLS LAST' in sql
    if key not in NUMERIC:
        assert '100/%/_' in compiled.params.values()

def test_sort_key_cannot_inject_sql():
    with pytest.raises(ValidationError):
        apply_register_query(select(Order.id), None, 'id; DROP TABLE users', True)

@pytest.mark.parametrize('exc,safe', [(httpx.ConnectTimeout('x'),True), (httpx.ConnectError('x'),True), (httpx.PoolTimeout('x'),True), (httpx.ReadTimeout('x'),False), (httpx.WriteError('x'),False), (ValueError('bad JSON'),False)])
def test_attachment_retries_only_before_request_sent(exc,safe):
    row=SimpleNamespace(command='send_message',payload={'attachments':[{'file_id':1}]})
    assert delivery.attachment_delivery_uncertain(row,exc) is not safe
    row.payload={}
    assert not delivery.attachment_delivery_uncertain(row,exc)

@pytest.mark.asyncio
@pytest.mark.parametrize('locked',[True,False])
async def test_two_workers_cannot_dispatch_same_outbox(monkeypatch,locked):
    connection=SimpleNamespace(scalar=AsyncMock(return_value=locked))
    @asynccontextmanager
    async def begin(): yield connection
    monkeypatch.setattr(delivery,'get_engine',lambda:SimpleNamespace(begin=begin))
    dispatch=AsyncMock()
    monkeypatch.setattr(delivery,'_dispatch_outbound_command',dispatch)
    await delivery.dispatch_outbound_command('dispatch_outbound',{'outbound_log_id':4879})
    assert dispatch.await_count == int(locked)
    assert connection.scalar.call_args.args[1] == {'key':'bot-outbound:4879'}

@pytest.mark.asyncio
async def test_interrupted_attachment_send_is_not_replayed(monkeypatch):
    from app.modules.db.models.enums import BotOutboundStatus
    row=SimpleNamespace(status=BotOutboundStatus.QUEUED,command='send_message',
        payload={'attachments':[{'file_id':1}]},last_error='delivery_in_progress')
    session=SimpleNamespace(commit=AsyncMock())
    @asynccontextmanager
    async def factory(): yield session
    monkeypatch.setattr(delivery,'get_session_factory',lambda:factory)
    monkeypatch.setattr(delivery,'BotOutboundLogRepository',lambda s:SimpleNamespace(get_by_id=AsyncMock(return_value=row)))
    bot_lookup=AsyncMock()
    monkeypatch.setattr(delivery,'BotRepository',lambda s:SimpleNamespace(get_by_id=bot_lookup))
    await delivery._dispatch_outbound_command('dispatch_outbound',{'outbound_log_id':4879})
    assert row.status == BotOutboundStatus.FAILED
    assert row.last_error.startswith('delivery_uncertain:')
    bot_lookup.assert_not_awaited()
    session.commit.assert_awaited_once()
