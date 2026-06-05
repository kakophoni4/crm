from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_takeover_starts_and_releases(
    client: AsyncClient,
    db_ready: None,
    chats_org: dict[str, object],
    senior_headers: dict[str, str],
) -> None:
    chat_id = chats_org["chat_ids"]["a"]

    start = await client.post(
        f"/api/v1/chats/{chat_id}/takeover",
        headers=senior_headers,
        json={"reason": "assist"},
    )
    assert start.status_code == 200, start.text
    assert start.json()["released_at"] is None

    release = await client.post(
        f"/api/v1/chats/{chat_id}/takeover/release",
        headers=senior_headers,
    )
    assert release.status_code == 200
    assert release.json()["released_at"] is not None
