from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_takeover_only_in_own_department(
    client: AsyncClient,
    db_ready: None,
    chats_org: dict[str, object],
    senior_other_headers: dict[str, str],
) -> None:
    chat_id = chats_org["chat_ids"]["a"]

    response = await client.post(
        f"/api/v1/chats/{chat_id}/takeover",
        headers=senior_other_headers,
        json={},
    )
    assert response.status_code == 403
