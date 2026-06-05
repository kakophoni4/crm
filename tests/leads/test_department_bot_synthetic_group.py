from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine, text

from app.modules.leads.department_inbox import DEPT_INBOX_GROUP_NAME
from app.shared.settings import Settings
from app.workers.bots.process_event import process_bot_event
from tests.auth.conftest import _sync_database_url
from tests.leads.conftest import (
    LEADS_DEPT_INBOX_PREFIX,
    LEADS_DEPT_TELEGRAM_USER_ID,
    build_leads_dept_inbound,
)

DEPT_SYNTH_EVENT_ID = f"{LEADS_DEPT_INBOX_PREFIX}0002"


@pytest.mark.asyncio
async def test_department_bot_inbound_creates_lead_on_synthetic_group(
    client: AsyncClient,
    leads_dept_bot_org: dict[str, int],
    test_settings: Settings,
    db_ready: None,
) -> None:
    del db_ready
    dept_id = leads_dept_bot_org["dept_id"]
    body, headers = build_leads_dept_inbound(
        DEPT_SYNTH_EVENT_ID,
        external_message_id="dept-msg-synth-1",
        text_body="department bot with synthetic group",
    )
    response = await client.post("/api/v1/bot-events", content=body, headers=headers)
    assert response.status_code == 202, response.text
    await process_bot_event("process_bot_event", {"event_id": DEPT_SYNTH_EVENT_ID})

    engine = create_engine(_sync_database_url(test_settings.database_url))
    try:
        with engine.connect() as conn:
            synth_group_id = conn.execute(
                text(
                    """
                    SELECT id FROM groups
                    WHERE department_id = :dept_id AND name = :name
                    """
                ),
                {"dept_id": dept_id, "name": DEPT_INBOX_GROUP_NAME},
            ).scalar_one()

            row = conn.execute(
                text(
                    """
                    SELECT c.assigned_group_id, c.assigned_department_id, m.lead_id, l.group_id
                    FROM chats c
                    JOIN messages m ON m.chat_id = c.id
                    JOIN contacts ct ON ct.id = c.contact_id
                    LEFT JOIN leads l ON l.id = m.lead_id
                    WHERE ct.telegram_user_id = :tg
                    ORDER BY m.id DESC
                    LIMIT 1
                    """
                ),
                {"tg": LEADS_DEPT_TELEGRAM_USER_ID},
            ).one()

            lead_count = conn.execute(
                text(
                    """
                    SELECT COUNT(*) FROM leads
                    WHERE contact_id IN (
                        SELECT id FROM contacts WHERE telegram_user_id = :tg
                    )
                    """
                ),
                {"tg": LEADS_DEPT_TELEGRAM_USER_ID},
            ).scalar_one()
    finally:
        engine.dispose()

    assert row.assigned_group_id is None
    assert row.assigned_department_id == dept_id
    assert row.lead_id is not None
    assert row.group_id == synth_group_id
    assert lead_count == 1
