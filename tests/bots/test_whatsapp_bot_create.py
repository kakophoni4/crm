from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_admin_creates_whatsapp_bot_with_green_credentials(
    client: AsyncClient,
    db_ready: None,
    admin_headers: dict[str, str],
    bots_org: dict[str, object],
) -> None:
    dept_id = bots_org["dept_id"]
    with patch(
        "app.modules.bots.service.sync_green_webhook",
        new_callable=AsyncMock,
    ) as sync_mock:
        response = await client.post(
            "/api/v1/bots",
            headers=admin_headers,
            json={
                "code": "wa_test_bot",
                "name": "WhatsApp Test",
                "channel": "whatsapp",
                "department_id": dept_id,
                "green_instance_id": "1105653814",
                "green_api_token": "test-green-token-32chars-minimum-xx",
                "green_api_url": "https://1105.api.green-api.com",
                "green_media_url": "https://1105.api.green-api.com",
            },
        )
    assert response.status_code == 201, response.text
    sync_mock.assert_awaited_once()
    data = response.json()
    assert data["channel"] == "whatsapp"
    assert data["green_instance_id"] == "1105653814"
    assert data["has_green_api_token"] is True
    assert data["whatsapp_webhook_url"] is not None
    assert "wa_test_bot" in data["whatsapp_webhook_url"]
    assert data["secrets"]["inbound_secret"]
    assert data["secrets"]["outbound_secret"]
    assert "test-green-token" not in response.text

    detail = await client.get(f"/api/v1/bots/{data['id']}", headers=admin_headers)
    assert detail.status_code == 200
    assert detail.json()["channel"] == "whatsapp"


@pytest.mark.asyncio
async def test_wa_bridge_config_lists_whatsapp_bot(
    client: AsyncClient,
    db_ready: None,
    admin_headers: dict[str, str],
    bots_org: dict[str, object],
    test_settings,
) -> None:
    dept_id = bots_org["dept_id"]
    with patch("app.modules.bots.service.sync_green_webhook", new_callable=AsyncMock):
        created = await client.post(
            "/api/v1/bots",
            headers=admin_headers,
            json={
                "code": "wa_bridge_cfg",
                "name": "WA Bridge",
                "channel": "whatsapp",
                "department_id": dept_id,
                "green_instance_id": "1105653814",
                "green_api_token": "bridge-test-token-32chars-minimum",
            },
        )
    assert created.status_code == 201

    config = await client.get(
        "/api/v1/internal/wa-bridge/config",
        headers={"X-Wa-Bridge-Secret": test_settings.wa_bridge_sync_secret},
    )
    assert config.status_code == 200
    codes = {item["bot_code"] for item in config.json()["items"]}
    assert "wa_bridge_cfg" in codes
