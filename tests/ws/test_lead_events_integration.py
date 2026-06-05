"""HG-8: WebSocket receives lead.created after inbound bot-event (real hub + Redis)."""

from __future__ import annotations

import asyncio
import time

from fastapi import FastAPI
from httpx import AsyncClient
from httpx_ws import aconnect_ws

from app.workers.bots.process_event import process_bot_event
from tests.leads.conftest import build_leads_cycle_inbound
from tests.realtime.conftest import receive_domain_event, wait_for_connected, ws_http_client


async def _ws_receive_lead_created(
    app: FastAPI,
    ws_connect_kwargs: dict[str, object],
    headers: dict[str, str],
) -> dict[str, object]:
    async with ws_http_client(app) as ws_client:
        ticket_resp = await ws_client.post(
            "/api/v1/auth/ws-ticket",
            headers=headers,
        )
        assert ticket_resp.status_code == 200, ticket_resp.text
        ticket = ticket_resp.json()["ticket"]
        url = f"/api/v1/ws?ticket={ticket}"

        async with aconnect_ws(url, ws_client, **ws_connect_kwargs) as ws:
            await wait_for_connected(ws)

            event_id = f"01LEADWS{int(time.time())}"
            body, inbound_headers = build_leads_cycle_inbound(
                event_id=event_id,
                external_message_id=f"lead-ws-msg-{event_id}",
                text="ws integration inbound",
            )
            post = await ws_client.post(
                "/api/v1/bot-events",
                content=body,
                headers=inbound_headers,
            )
            assert post.status_code == 202, post.text
            await process_bot_event("process_bot_event", {"event_id": event_id})

            return await receive_domain_event(ws, timeout=5.0)


async def test_lead_created_after_bot_event(
    app: FastAPI,
    client: AsyncClient,
    ws_connect_kwargs: dict[str, object],
    db_ready: None,
    realtime_hub: None,
    leads_cycle_org: dict[str, object],
) -> None:
    del db_ready
    from tests.chats.conftest import login

    token = await login(
        client,
        str(leads_cycle_org["operator_email"]),
        str(leads_cycle_org["password"]),
    )
    headers = {"Authorization": f"Bearer {token}"}

    message = await asyncio.wait_for(
        _ws_receive_lead_created(app, ws_connect_kwargs, headers),
        timeout=10.0,
    )

    assert message["type"] == "lead.created"
    assert message["topic"] == "lead.created"
    payload = message["payload"]
    assert isinstance(payload, dict)
    assert payload.get("source") == "inbound"
    assert isinstance(payload.get("lead_id"), int)
    assert isinstance(payload.get("chat_id"), int)
    assert isinstance(payload.get("group_id"), int)
