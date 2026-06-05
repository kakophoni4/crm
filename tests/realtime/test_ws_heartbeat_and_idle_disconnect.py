from __future__ import annotations

import asyncio
import time

import pytest
from fastapi import FastAPI
from httpx_ws import WebSocketDisconnect, aconnect_ws

from app.shared.settings import get_settings
from tests.realtime.conftest import wait_for_connected, ws_http_client


async def test_ws_heartbeat_and_idle_disconnect(
    app: FastAPI,
    ws_connect_kwargs: dict[str, object],
    db_ready: None,
    realtime_hub: None,
    auth_user: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "ws_heartbeat_interval_seconds", 0.05)
    monkeypatch.setattr(settings, "ws_idle_timeout_seconds", 0.25)

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
            await ws.send_json({"type": "ping"})
            deadline = time.monotonic() + 2.0
            pong: dict[str, object] | None = None
            while time.monotonic() < deadline:
                message = await ws.receive_json(timeout=0.5)
                if message == {"type": "pong"}:
                    pong = message
                    break
            assert pong == {"type": "pong"}
            await asyncio.sleep(0.35)
            disconnected = False
            deadline = time.monotonic() + 1.0
            while time.monotonic() < deadline:
                try:
                    await ws.receive_json(timeout=0.2)
                except (WebSocketDisconnect, TimeoutError):
                    disconnected = True
                    break
            assert disconnected
