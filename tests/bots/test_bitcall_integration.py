from __future__ import annotations

import json
import time
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine, text

from app.modules.bots.hmac_util import sign_inbound
from app.workers.bots.process_event import process_bot_event
from tests.auth.conftest import _sync_database_url

BITCALL_INBOUND_SECRET = "bitcall-inbound-secret-32chars-min"
BITCALL_OUTBOUND_SECRET = "bitcall-outbound-secret-32chars-min"


def _bitcall_headers(event_id: str, body: bytes, bot_code: str) -> dict[str, str]:
    ts = str(int(time.time()))
    return {
        "X-Bot-Code": bot_code,
        "X-Event-Id": event_id,
        "X-Timestamp": ts,
        "X-Signature": sign_inbound(event_id, ts, body, BITCALL_INBOUND_SECRET),
        "Content-Type": "application/json",
    }


def _bitcall_call_payload(
    *,
    event_id: str,
    bot_code: str,
    phone: str,
    external_id: str,
) -> bytes:
    envelope = {
        "event": "call.received",
        "event_id": event_id,
        "occurred_at": "2026-06-22T12:00:00Z",
        "bot_code": bot_code,
        "payload": {
            "contact": {
                "phone": phone,
                "full_name": "Bitcall Client",
            },
            "call": {
                "external_id": external_id,
                "direction": "inbound",
                "status": "completed",
                "duration_seconds": 42,
                "recording_url": "https://bitcall.example.test/recordings/call-001.mp3",
            },
        },
    }
    return json.dumps(envelope, separators=(",", ":")).encode("utf-8")


@pytest.mark.asyncio
async def test_admin_creates_bitcall_bot(
    client: AsyncClient,
    db_ready: None,
    admin_headers: dict[str, str],
    bots_org: dict[str, object],
) -> None:
    dept_id = bots_org["dept_id"]
    response = await client.post(
        "/api/v1/bots",
        headers=admin_headers,
        json={
            "code": "bitcall_create_test",
            "name": "Bitcall Create Test",
            "channel": "bitcall",
            "department_id": dept_id,
            "outbound_url": "https://bitcall.example.test/crm/calls",
            "inbound_secret": BITCALL_INBOUND_SECRET,
            "outbound_secret": BITCALL_OUTBOUND_SECRET,
        },
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["channel"] == "bitcall"
    assert data["outbound_url"] == "https://bitcall.example.test/crm/calls"
    assert data["secrets"]["inbound_secret"] == BITCALL_INBOUND_SECRET
    assert data["secrets"]["outbound_secret"] == BITCALL_OUTBOUND_SECRET


@pytest.mark.asyncio
async def test_bitcall_call_received_creates_contact_chat_lead_and_message(
    client: AsyncClient,
    db_ready: None,
    admin_headers: dict[str, str],
    bots_org: dict[str, object],
    test_settings,
) -> None:
    dept_id = int(bots_org["dept_id"])
    group_id = int(bots_org["group_id"])
    phone = "+79005550123"
    event_id = "bitcall-call-001"
    bot_code = "bitcall_ingest_test"

    engine = create_engine(_sync_database_url(test_settings.database_url))
    try:
        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM messages WHERE external_event_id = :event_id"),
                {"event_id": event_id},
            )
            connection.execute(
                text("DELETE FROM bot_events_inbox WHERE event_id = :event_id"),
                {"event_id": event_id},
            )
            connection.execute(
                text(
                    """
                    DELETE FROM chats
                    WHERE contact_id IN (SELECT id FROM contacts WHERE phone = :phone)
                    """
                ),
                {"phone": phone},
            )
            connection.execute(text("DELETE FROM contacts WHERE phone = :phone"), {"phone": phone})
            connection.execute(text("DELETE FROM bots WHERE code = :code"), {"code": bot_code})
    finally:
        engine.dispose()

    created = await client.post(
        "/api/v1/bots",
        headers=admin_headers,
        json={
            "code": bot_code,
            "name": "Bitcall Ingest Test",
            "channel": "bitcall",
            "department_id": dept_id,
            "outbound_url": "https://bitcall.example.test/crm/calls",
            "inbound_secret": BITCALL_INBOUND_SECRET,
            "outbound_secret": BITCALL_OUTBOUND_SECRET,
        },
    )
    assert created.status_code == 201, created.text
    bot_id = created.json()["id"]

    assigned = await client.put(
        f"/api/v1/bots/{bot_id}/group-assignments",
        headers=admin_headers,
        json={"group_ids": [group_id]},
    )
    assert assigned.status_code == 200, assigned.text

    body = _bitcall_call_payload(
        event_id=event_id,
        bot_code=bot_code,
        phone=phone,
        external_id="bitcall-call-ext-001",
    )
    with patch("app.modules.bots.service.enqueue", new_callable=AsyncMock):
        response = await client.post(
            "/api/v1/bot-events",
            content=body,
            headers=_bitcall_headers(event_id, body, bot_code),
        )
    assert response.status_code == 202, response.text
    assert response.json()["status"] == "accepted"

    await process_bot_event("process_bot_event", {"event_id": event_id})

    engine = create_engine(_sync_database_url(test_settings.database_url))
    try:
        with engine.connect() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT
                        c.phone,
                        c.full_name,
                        ch.bot_id,
                        m.text,
                        m.kind,
                        m.attachments,
                        l.group_id
                    FROM contacts c
                    JOIN chats ch ON ch.contact_id = c.id
                    JOIN messages m ON m.chat_id = ch.id
                    JOIN leads l ON l.id = m.lead_id
                    WHERE c.phone = :phone
                    """
                ),
                {"phone": phone},
            ).one()
            inbox_status = connection.execute(
                text("SELECT status FROM bot_events_inbox WHERE event_id = :event_id"),
                {"event_id": event_id},
            ).scalar_one()
    finally:
        engine.dispose()

    assert inbox_status == "done"
    assert row.phone == phone
    assert row.full_name == "Bitcall Client"
    assert int(row.bot_id) == int(bot_id)
    assert "Bitcall inbound call" in row.text
    assert row.kind == "voice"
    assert row.attachments[0]["url"].endswith("/call-001.mp3")
    assert int(row.group_id) == group_id
