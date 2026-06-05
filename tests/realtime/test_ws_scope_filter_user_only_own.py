from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx_ws import aconnect_ws

from app.realtime.events import publish
from tests.realtime.conftest import receive_domain_event, wait_for_connected, ws_http_client


async def test_ws_scope_filter_user_only_own(
    app: FastAPI,
    ws_connect_kwargs: dict[str, object],
    db_ready: None,
    realtime_hub: None,
    chats_org: dict[str, object],
    operator_a_headers: dict[str, str],
) -> None:
    emails = chats_org["emails"]
    user_ids = chats_org["user_ids"]
    assert isinstance(emails, dict)
    assert isinstance(user_ids, dict)
    user_a_id = int(user_ids[str(emails["operator_a"])])
    dept_b = int(chats_org["dept_b"])

    async with ws_http_client(app) as ws_client:
        ticket_resp = await ws_client.post(
            "/api/v1/auth/ws-ticket",
            headers=operator_a_headers,
        )
        assert ticket_resp.status_code == 200
        ticket = ticket_resp.json()["ticket"]
        url = f"/api/v1/ws?ticket={ticket}"

        async with aconnect_ws(url, ws_client, **ws_connect_kwargs) as ws:
            await wait_for_connected(ws)
            await publish(
                "chat.message.inbound",
                {"chat_id": 999, "message_id": 1},
                scope={"department_id": dept_b},
            )
            await publish(
                "chat.message.inbound",
                {"chat_id": 1, "message_id": 2},
                scope={"user_id": user_a_id},
            )
            message = await receive_domain_event(ws)
            assert message["payload"]["message_id"] == 2
            with pytest.raises(TimeoutError):
                await receive_domain_event(ws, timeout=0.5)
