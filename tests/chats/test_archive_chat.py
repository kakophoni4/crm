from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_archive_chat(
    client: AsyncClient,
    db_ready: None,
    chats_org: dict[str, object],
    operator_b_headers: dict[str, str],
) -> None:
    chat_id = chats_org["chat_ids"]["b"]

    response = await client.post(
        f"/api/v1/chats/{chat_id}/archive",
        headers=operator_b_headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "archived"
