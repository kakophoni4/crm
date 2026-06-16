from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine, text

from app.workers.bots.process_event import process_bot_event
from tests.auth.conftest import _sync_database_url
from tests.bots.conftest import INBOUND_SECRET, build_inbound_payload


@pytest.mark.asyncio
async def test_inbound_creates_separate_chat_per_bot(
    client: AsyncClient,
    db_ready: None,
    test_settings,
    bots_org: dict[str, object],
) -> None:
    """Each bot gets its own open chat for the same contact."""
    engine = create_engine(_sync_database_url(test_settings.database_url))
    dept_id = int(bots_org["dept_id"])
    group_id = int(bots_org["group_id"])
    bot_a_id = int(bots_org["bot_id"])
    key = test_settings.pgcrypto_key

    try:
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM messages WHERE external_event_id LIKE 'bot-per-bot-%'"))
            connection.execute(text("DELETE FROM bot_events_inbox WHERE event_id LIKE 'bot-per-bot-%'"))
            connection.execute(
                text(
                    """
                    DELETE FROM chats
                    WHERE contact_id IN (SELECT id FROM contacts WHERE telegram_user_id = 999003)
                    """
                ),
            )
            connection.execute(text("DELETE FROM contacts WHERE telegram_user_id = 999003"))
            connection.execute(text("DELETE FROM bots WHERE code = 'test_bot_b'"))

            connection.execute(
                text(
                    """
                    INSERT INTO bots (
                        code, name, owner_type, owner_id, department_id,
                        inbound_secret_encrypted, outbound_secret_encrypted,
                        outbound_url, is_active
                    )
                    VALUES (
                        'test_bot_b', 'Test Bot B',
                        'group', :group_id, :dept_id,
                        pgp_sym_encrypt(:in_secret, :key),
                        pgp_sym_encrypt(:out_secret, :key),
                        'https://bot.example.com/crm/cmd',
                        TRUE
                    )
                    """
                ),
                {
                    "group_id": group_id,
                    "dept_id": dept_id,
                    "in_secret": INBOUND_SECRET,
                    "out_secret": "test-outbound-secret-32chars-minimum",
                    "key": key,
                },
            )
            bot_b_id = connection.execute(
                text("SELECT id FROM bots WHERE code = 'test_bot_b'"),
            ).scalar_one()

            admin_id = connection.execute(
                text("SELECT id FROM users WHERE role = 'admin' ORDER BY id LIMIT 1"),
            ).scalar_one()
            contact_id = connection.execute(
                text(
                    """
                    INSERT INTO contacts (telegram_user_id, full_name, created_by)
                    VALUES (999003, 'Per Bot Test', :uid)
                    RETURNING id
                    """
                ),
                {"uid": admin_id},
            ).scalar_one()
            chat_a_id = connection.execute(
                text(
                    """
                    INSERT INTO chats (
                        contact_id, bot_id, assigned_group_id, assigned_department_id, status
                    )
                    VALUES (:cid, :bid, :gid, :did, 'open')
                    RETURNING id
                    """
                ),
                {
                    "cid": contact_id,
                    "bid": bot_a_id,
                    "gid": group_id,
                    "did": dept_id,
                },
            ).scalar_one()
    finally:
        engine.dispose()

    event_id = "bot-per-bot-001"
    body, headers = build_inbound_payload(
        event_id=event_id,
        external_id="msg_per_bot_001",
        text="hello on bot b",
        telegram_user_id=999003,
        bot_code="test_bot_b",
    )

    with patch("app.modules.bots.service.enqueue", new_callable=AsyncMock):
        response = await client.post("/api/v1/bot-events", content=body, headers=headers)
    assert response.status_code == 202, response.text

    await process_bot_event("process_bot_event", {"event_id": event_id})

    engine = create_engine(_sync_database_url(test_settings.database_url))
    try:
        with engine.connect() as connection:
            inbox = connection.execute(
                text("SELECT status FROM bot_events_inbox WHERE event_id = :eid"),
                {"eid": event_id},
            ).one()
            message = connection.execute(
                text(
                    """
                    SELECT chat_id, text FROM messages
                    WHERE external_message_id = 'msg_per_bot_001'
                    """
                ),
            ).one()
            open_chats = connection.execute(
                text(
                    """
                    SELECT id, bot_id FROM chats
                    WHERE contact_id = :cid AND status != 'archived'
                    ORDER BY id
                    """
                ),
                {"cid": contact_id},
            ).all()
    finally:
        engine.dispose()

    assert inbox[0] == "done"
    assert int(message[0]) != int(chat_a_id)
    assert message[1] == "hello on bot b"
    assert len(open_chats) == 2
    assert {int(row[1]) for row in open_chats} == {bot_a_id, bot_b_id}
