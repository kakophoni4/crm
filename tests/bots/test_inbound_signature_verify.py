from __future__ import annotations

import json
import time

import pytest
from httpx import AsyncClient

from tests.bots.conftest import INBOUND_SECRET, build_inbound_payload, sign_event


@pytest.mark.asyncio
async def test_valid_signature_returns_202(
    client: AsyncClient,
    db_ready: None,
    bots_org: dict[str, object],
) -> None:
    body, headers = build_inbound_payload(event_id="01J5SIGVALID001")
    response = await client.post("/api/v1/bot-events", content=body, headers=headers)
    assert response.status_code == 202, response.text
    assert response.json()["status"] == "accepted"


@pytest.mark.asyncio
async def test_invalid_signature_returns_401(
    client: AsyncClient,
    db_ready: None,
    bots_org: dict[str, object],
) -> None:
    body, headers = build_inbound_payload(event_id="01J5SIGBAD00001")
    headers["X-Signature"] = "deadbeef" * 8
    response = await client.post("/api/v1/bot-events", content=body, headers=headers)
    assert response.status_code == 401
    assert "inbound_secret" not in response.text.lower()
    assert "signature" not in response.json().get("error", {}).get("message", "").lower()


@pytest.mark.asyncio
async def test_expired_timestamp_returns_401(
    client: AsyncClient,
    db_ready: None,
    bots_org: dict[str, object],
) -> None:
    event_id = "01J5SIGEXP00001"
    envelope = {
        "event": "message.received",
        "event_id": event_id,
        "bot_code": "test_bot_a",
        "payload": {"contact": {"telegram_user_id": 1}, "message": {"external_id": "x"}},
    }
    body = json.dumps(envelope).encode()
    old_ts = str(int(time.time()) - 400)
    headers = {
        "X-Bot-Code": "test_bot_a",
        "X-Event-Id": event_id,
        "X-Timestamp": old_ts,
        "X-Signature": sign_event(event_id, old_ts, body, INBOUND_SECRET),
        "Content-Type": "application/json",
    }
    response = await client.post("/api/v1/bot-events", content=body, headers=headers)
    assert response.status_code == 401
