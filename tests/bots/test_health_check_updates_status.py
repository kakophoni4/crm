from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.workers.bots.health_check import bot_health_check


@pytest.mark.asyncio
async def test_health_check_updates_bot_status(
    client: AsyncClient,
    db_ready: None,
    admin_headers: dict[str, str],
    bots_org: dict[str, object],
) -> None:
    bot_id = int(bots_org["bot_id"])

    mock_response = AsyncMock()
    mock_response.status_code = 200

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        await bot_health_check("bot_health_check", {"bot_id": bot_id})

    detail = await client.get(f"/api/v1/bots/{bot_id}", headers=admin_headers)
    assert detail.status_code == 200
    assert detail.json()["last_health_status"] == "healthy"
    assert detail.json()["last_health_checked_at"] is not None
