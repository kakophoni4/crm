import gzip
import json
from types import SimpleNamespace

import httpx
import pytest
from pydantic import SecretStr

from app.modules.ai import client
from app.modules.ai.imports import prepare
from app.modules.ai.router import admin
from app.shared.exceptions import AppError, PermissionDenied


@pytest.mark.asyncio
async def test_admin_boundary():
    with pytest.raises(PermissionDenied):
        await admin(SimpleNamespace(role="kesher"))
    actor = SimpleNamespace(role="admin")
    assert await admin(actor) is actor


@pytest.mark.asyncio
async def test_external_unauthorized_does_not_invalidate_crm_session(monkeypatch):
    monkeypatch.setattr(client.settings, "ai_service_admin_key", SecretStr("fixture-key"))
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            401, json={"error": {"code": "unauthorized", "message": "bad key"}}
        )
    )
    async with httpx.AsyncClient(transport=transport) as http:
        monkeypatch.setattr(client, "_client", http)
        with pytest.raises(AppError) as error:
            await client.call("GET", "connection")
        assert error.value.status == 502
        assert error.value.code == "ai_key_invalid"
        assert "fixture-key" not in str(error.value)


def test_preparation_masks_data_and_excludes_target_from_context():
    raw = json.dumps(
        {
            "chat": {"id": 17},
            "messages": [
                {
                    "id": 2,
                    "created_at": "2026-01-01T00:01",
                    "direction": "outbound",
                    "sender_user_id": 3,
                    "text": "Ответ на example@example.com",
                },
                {
                    "id": 1,
                    "created_at": "2026-01-01T00:00",
                    "direction": "inbound",
                    "text": "Напишите на example@example.com",
                },
            ],
        }
    ).encode()
    result = prepare(gzip.compress(raw))
    record = result["records"][0]
    assert record["messages"] == [{"role": "user", "content": "Напишите на [ДАННЫЕ_1]"}]
    assert record["answer"]["reply"] == "Ответ на [ДАННЫЕ_1]"
    assert record["system"] == ""
    assert record["chat_id"] != "17"


def test_corrupt_archive_is_rejected():
    with pytest.raises(AppError):
        prepare(b"\x1f\x8bcorrupt")


def test_oversize_decompressed_archive_is_rejected(monkeypatch):
    from app.modules.ai import imports

    monkeypatch.setattr(imports, "MAX_BYTES", 128)
    with pytest.raises(AppError) as error:
        prepare(gzip.compress(b"x" * 1024))
    assert error.value.status == 413
