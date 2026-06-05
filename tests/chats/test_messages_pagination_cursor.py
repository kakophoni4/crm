from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_messages_pagination_cursor(
    client: AsyncClient,
    db_ready: None,
    chats_org: dict[str, object],
    operator_a_headers: dict[str, str],
) -> None:
    chat_id = chats_org["chat_ids"]["a"]

    for idx in range(3):
        resp = await client.post(
            f"/api/v1/chats/{chat_id}/messages",
            headers=operator_a_headers,
            json={"text": f"msg-{idx}", "idempotency_key": f"pag-{idx}"},
        )
        assert resp.status_code == 202

    first = await client.get(
        f"/api/v1/chats/{chat_id}/messages",
        headers=operator_a_headers,
        params={"limit": 2},
    )
    assert first.status_code == 200
    body = first.json()
    assert len(body["items"]) == 2
    assert body["next_cursor"] is not None

    second = await client.get(
        f"/api/v1/chats/{chat_id}/messages",
        headers=operator_a_headers,
        params={"limit": 2, "cursor": body["next_cursor"]},
    )
    assert second.status_code == 200
    assert len(second.json()["items"]) >= 1
