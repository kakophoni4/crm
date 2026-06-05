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
