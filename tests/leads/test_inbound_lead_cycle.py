from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine, text

from app.shared.settings import Settings
from app.workers.bots.process_event import process_bot_event
from tests.auth.conftest import _sync_database_url
from tests.chats.conftest import login
from tests.leads.conftest import LEADS_CYCLE_TELEGRAM_USER_ID, build_leads_cycle_inbound


async def _post_and_process(
    client: AsyncClient,
    *,
    event_id: str,
    external_message_id: str,
    text_body: str,
) -> None:
    body, headers = build_leads_cycle_inbound(
        event_id=event_id,
        external_message_id=external_message_id,
        text=text_body,
    )
    response = await client.post("/api/v1/bot-events", content=body, headers=headers)
    assert response.status_code == 202, response.text
    assert response.json()["status"] == "accepted"
    await process_bot_event("process_bot_event", {"event_id": event_id})


@pytest.mark.asyncio
async def test_inbound_lead_close_reopen_cycle(
    client: AsyncClient,
    leads_cycle_org: dict[str, object],
    test_settings: Settings,
    db_ready: None,
) -> None:
    del db_ready
    await _post_and_process(
        client,
        event_id="01LEADCYCLE0001",
        external_message_id="lc-msg-1",
        text_body="first inbound",
    )

    engine = create_engine(_sync_database_url(test_settings.database_url))
    try:
        with engine.connect() as conn:
            contact_id = conn.execute(
                text(
                    """
                    SELECT id FROM contacts
                    WHERE telegram_user_id = :tg
                    """
                ),
                {"tg": LEADS_CYCLE_TELEGRAM_USER_ID},
            ).scalar_one()
            row = conn.execute(
                text(
                    """
                    SELECT c.id AS chat_id, c.current_lead_id, m.id AS message_id, m.lead_id
                    FROM chats c
                    JOIN messages m ON m.chat_id = c.id
                    WHERE c.contact_id = :cid
                    ORDER BY m.id
                    LIMIT 1
                    """
                ),
                {"cid": contact_id},
            ).one()
            lead_count = conn.execute(
                text(
                    """
                    SELECT COUNT(*) FROM leads
                    WHERE contact_id = :cid AND closed_at IS NULL
                    """
                ),
                {"cid": contact_id},
            ).scalar_one()
    finally:
        engine.dispose()

    assert lead_count == 1
    lead_id_1 = int(row.current_lead_id)
    message_id_1 = int(row.message_id)
    chat_id = int(row.chat_id)
    assert int(row.lead_id) == lead_id_1
    assert lead_id_1 > 0

    token = await login(
        client,
        str(leads_cycle_org["operator_email"]),
        str(leads_cycle_org["password"]),
    )
    close_resp = await client.post(
        f"/api/v1/leads/{lead_id_1}/close",
        headers={"Authorization": f"Bearer {token}"},
        json={"status_id": leads_cycle_org["pipeline_won"]},
    )
    assert close_resp.status_code == 200, close_resp.text
    assert close_resp.json()["closed_at"] is not None

    await _post_and_process(
        client,
        event_id="01LEADCYCLE0002",
        external_message_id="lc-msg-2",
        text_body="second inbound after close",
    )

    engine = create_engine(_sync_database_url(test_settings.database_url))
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT id, lead_id FROM messages
                    WHERE chat_id = :chat_id
                    ORDER BY id
                    """
                ),
                {"chat_id": chat_id},
            ).all()
            current_lead_id = conn.execute(
                text("SELECT current_lead_id FROM chats WHERE id = :cid"),
                {"cid": chat_id},
            ).scalar_one()
            open_count = conn.execute(
                text(
                    """
                    SELECT COUNT(*) FROM leads
                    WHERE contact_id = :cid AND closed_at IS NULL
                    """
                ),
                {"cid": contact_id},
            ).scalar_one()
    finally:
        engine.dispose()

    assert len(rows) == 2
    assert rows[0][1] == lead_id_1
    lead_id_2 = int(rows[1][1])
    assert lead_id_2 != lead_id_1
    assert int(current_lead_id) == lead_id_2
    assert open_count == 1
    assert rows[0][0] == message_id_1
