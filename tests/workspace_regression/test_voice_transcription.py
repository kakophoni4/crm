from types import SimpleNamespace
from unittest.mock import AsyncMock
import httpx
import pytest
from app.modules.chats import transcription as mod

@pytest.mark.asyncio
async def test_cached_text_still_checks_scope():
    service=SimpleNamespace(get_attachment_info=AsyncMock(return_value={'transcript':'Привет'}))
    db=SimpleNamespace(execute=AsyncMock(),commit=AsyncMock())
    assert await mod.attachment_transcription('POST',service,db,'actor',1,2,0)=={'status':'ready','text':'Привет'}
    service.get_attachment_info.assert_awaited_once_with('actor',1,2,0)
    db.execute.assert_not_awaited()

@pytest.mark.asyncio
async def test_unauthorized_never_contacts_speech():
    service=SimpleNamespace(get_attachment_info=AsyncMock(side_effect=PermissionError))
    with pytest.raises(PermissionError):
        await mod.attachment_transcription('POST',service,None,'actor',1,2,0)

@pytest.mark.asyncio
async def test_oga_result_saved_without_replacing_other_attachments(monkeypatch):
    service=SimpleNamespace(get_attachment_info=AsyncMock(return_value={'filename':'file_1695.oga','storage_key':'private/key'}))
    db=SimpleNamespace(execute=AsyncMock(),commit=AsyncMock())
    client=httpx.AsyncClient
    transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'status':'ready','text':'Тест'}))
    monkeypatch.setattr(mod.httpx,'AsyncClient',lambda **kw:client(transport=transport,**kw))
    assert await mod.attachment_transcription('GET',service,db,'actor',1,2,0)=={'status':'ready','text':'Тест'}
    sql,params=db.execute.await_args.args
    assert 'jsonb_set' in str(sql)
    assert params['path']==['0','transcript']
    assert params['key']=='private/key'
    db.commit.assert_awaited_once()

@pytest.mark.asyncio
async def test_unavailable_has_safe_error(monkeypatch):
    service=SimpleNamespace(get_attachment_info=AsyncMock(return_value={'type':'voice','storage_key':'secret'}))
    def offline(request): raise httpx.ConnectError('private address',request=request)
    client=httpx.AsyncClient
    monkeypatch.setattr(mod.httpx,'AsyncClient',lambda **kw:client(transport=httpx.MockTransport(offline),**kw))
    result=await mod.attachment_transcription('POST',service,None,'actor',1,2,0)
    assert result['status']=='failed'
    assert 'private address' not in result['error']
