from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_secrets_only_on_create_not_on_get(
    client: AsyncClient,
    db_ready: None,
    admin_headers: dict[str, str],
    bots_org: dict[str, object],
) -> None:
    bot_id = bots_org["bot_id"]
    detail = await client.get(f"/api/v1/bots/{bot_id}", headers=admin_headers)
    assert detail.status_code == 200
    body = detail.json()
    assert "secrets" not in body
    assert "inbound_secret" not in body
    assert "outbound_secret" not in body
    assert "inbound_secret_encrypted" not in body
