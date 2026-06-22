from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_whatsapp_outreach_creates_chat(
    client: AsyncClient,
    db_ready: None,
    chats_org: dict[str, object],
    operator_a_headers: dict[str, str],
    admin_headers: dict[str, str],
) -> None:
    group_id = int(chats_org["group_a"])
    dept_id = int(chats_org["dept_a"])

    with patch("app.modules.bots.service.sync_green_webhook", new_callable=AsyncMock):
        bot_resp = await client.post(
            "/api/v1/bots",
            headers=admin_headers,
            json={
                "code": "wa_outreach_test",
                "name": "WA Outreach Test",
                "channel": "whatsapp",
                "department_id": dept_id,
                "owner_type": "group",
                "owner_id": group_id,
                "green_instance_id": "1105653999",
                "green_api_token": "outreach-test-token-32chars-minimum",
            },
        )
    assert bot_resp.status_code == 201, bot_resp.text
    bot_id = bot_resp.json()["id"]

    assign_resp = await client.put(
        f"/api/v1/bots/{bot_id}/group-assignments",
        headers=admin_headers,
        json={"group_ids": [group_id]},
    )
    assert assign_resp.status_code == 200, assign_resp.text

    outreach = await client.post(
        "/api/v1/chats/whatsapp-outreach",
        headers=operator_a_headers,
        json={
            "phone": "+7 900 123-45-67",
            "full_name": "Новый WA клиент",
            "bot_id": bot_id,
        },
    )
    assert outreach.status_code == 200, outreach.text
    body = outreach.json()
    assert body["created_chat"] is True
    assert body["chat_id"] > 0
    assert body["contact_id"] > 0

    chat = await client.get(f"/api/v1/chats/{body['chat_id']}", headers=operator_a_headers)
    assert chat.status_code == 200, chat.text

    again = await client.post(
        "/api/v1/chats/whatsapp-outreach",
        headers=operator_a_headers,
        json={
            "phone": "79001234567",
            "full_name": "Новый WA клиент",
            "bot_id": bot_id,
        },
    )
    assert again.status_code == 200, again.text
    assert again.json()["created_chat"] is False
    assert again.json()["chat_id"] == body["chat_id"]
