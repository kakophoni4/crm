from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx_ws import WebSocketDisconnect, aconnect_ws

from tests.realtime.conftest import ws_http_client


async def test_ws_ticket_one_time_use(
    app: FastAPI,
    ws_connect_kwargs: dict[str, object],
    db_ready: None,
    realtime_hub: None,
    auth_user: dict[str, object],
) -> None:
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
            connected = await ws.receive_json()
            assert connected["type"] == "connected"

        with pytest.raises(WebSocketDisconnect) as exc_info:
            async with aconnect_ws(url, ws_client, **ws_connect_kwargs):
                pass
        assert exc_info.value.code == 4401
