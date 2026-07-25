from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_idempotency_outbound(
    client: AsyncClient,
    db_ready: None,
    chats_org: dict[str, object],
    operator_a_headers: dict[str, str],
) -> None:
    chat_id = chats_org["chat_ids"]["a"]
    key = "same-idempotency-key"

    first = await client.post(
        f"/api/v1/chats/{chat_id}/messages",
        headers=operator_a_headers,
        json={"text": "once", "idempotency_key": key},
    )
    assert first.status_code == 202
    first_id = first.json()["id"]

    second = await client.post(
        f"/api/v1/chats/{chat_id}/messages",
        headers=operator_a_headers,
        json={"text": "once again", "idempotency_key": key},
    )
    assert second.status_code == 202
    assert second.json()["id"] == first_id

    listed = await client.get(
        f"/api/v1/chats/{chat_id}/messages",
        headers=operator_a_headers,
    )
    matching = [m for m in listed.json()["items"] if m.get("idempotency_key") == key]
    assert len(matching) == 1


@pytest.mark.asyncio
async def test_idempotency_key_rejected_for_other_chat(
    client: AsyncClient,
    db_ready: None,
    chats_org: dict[str, object],
    operator_a_headers: dict[str, str],
) -> None:
    chat_ids = chats_org["chat_ids"]
    assert isinstance(chat_ids, dict)
    chat_a = chat_ids["a"]
    chat_b = chat_ids["b"]
    key = "cross-chat-idempotency-key"

    first = await client.post(
        f"/api/v1/chats/{chat_a}/messages",
        headers=operator_a_headers,
        json={"text": "in chat a", "idempotency_key": key},
    )
    assert first.status_code == 202

    second = await client.post(
        f"/api/v1/chats/{chat_b}/messages",
        headers=operator_a_headers,
        json={"text": "in chat b", "idempotency_key": key},
    )
    assert second.status_code == 422
    assert "idempotency_key" in second.text.lower() or "another chat" in second.text.lower()
