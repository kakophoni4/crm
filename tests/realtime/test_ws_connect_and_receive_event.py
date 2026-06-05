from __future__ import annotations

from fastapi import FastAPI
from httpx_ws import aconnect_ws

from app.realtime.events import publish
from tests.realtime.conftest import receive_domain_event, wait_for_connected, ws_http_client


async def test_ws_connect_and_receive_event(
    app: FastAPI,
    ws_connect_kwargs: dict[str, object],
    db_ready: None,
    realtime_hub: None,
    auth_user: dict[str, object],
) -> None:
    user = auth_user["user"]
    assert isinstance(user, dict)
    user_id = int(user["id"])
    token = auth_user["access_token"]
    assert isinstance(token, str)

    async with ws_http_client(app) as ws_client:
        ticket_resp = await ws_client.post(
            "/api/v1/auth/ws-ticket",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert ticket_resp.status_code == 200
        ticket = ticket_resp.json()["ticket"]
        url = f"/api/v1/ws?ticket={ticket}"

        async with aconnect_ws(url, ws_client, **ws_connect_kwargs) as ws:
            await wait_for_connected(ws)
            await publish(
                "chat.message.inbound",
                {"chat_id": 1, "message_id": 99},
                scope={"user_id": user_id},
            )
            message = await receive_domain_event(ws)

    assert message["type"] == "chat.message.inbound"
    assert message["topic"] == "chat.message.inbound"
    assert message["payload"]["message_id"] == 99
