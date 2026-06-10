from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine, text

from app.shared.settings import Settings
from tests.auth.conftest import _sync_database_url


@pytest.mark.asyncio
async def test_send_outbound_message_publishes_event(
    client: AsyncClient,
    db_ready: None,
    chats_org: dict[str, object],
    operator_a_headers: dict[str, str],
    test_settings: Settings,
) -> None:
    chat_ids = chats_org["chat_ids"]
    contact_ids = chats_org["contact_ids"]
    dept_a = int(chats_org["dept_a"])
    assert isinstance(chat_ids, dict)
    assert isinstance(contact_ids, dict)
    chat_id = chat_ids["a"]
    contact_id = int(contact_ids["a"])
    telegram_user_id = 900_000_000 + contact_id

    engine = create_engine(_sync_database_url(test_settings.database_url))
    try:
        with engine.begin() as connection:
            bot_id = connection.execute(
                text(
                    """
                    INSERT INTO bots (
                        code, name, owner_type, owner_id, department_id,
                        inbound_secret_encrypted, outbound_secret_encrypted,
                        outbound_url, health_url, is_active
                    )
                    VALUES (
                        :code, 'Chats Outbound Bot',
                        'department', :dept_id, :dept_id,
                        pgp_sym_encrypt(:in_secret, :key),
                        pgp_sym_encrypt(:out_secret, :key),
                        'https://bot.example.com/crm/cmd',
                        'https://bot.example.com/crm/health',
                        TRUE
                    )
                    ON CONFLICT (code) DO UPDATE SET owner_id = EXCLUDED.owner_id
                    RETURNING id
                    """
                ),
                {
                    "code": "chats_outbound_test_bot",
                    "dept_id": dept_a,
                    "in_secret": "test-inbound-secret-32chars-minimum",
                    "out_secret": "test-outbound-secret-32chars-minimum",
                    "key": test_settings.pgcrypto_key,
                },
            ).scalar_one()
            connection.execute(
                text("UPDATE contacts SET telegram_user_id = :tg WHERE id = :cid"),
                {"tg": telegram_user_id, "cid": contact_id},
            )
            connection.execute(
                text("UPDATE chats SET bot_id = :bot_id WHERE id = :chat_id"),
                {"bot_id": bot_id, "chat_id": chat_id},
            )
    finally:
        engine.dispose()

    with (
        patch("app.modules.chats.messages.publish", new_callable=AsyncMock) as mock_publish,
        patch("app.workers.bots.dispatch_outbound.enqueue", new_callable=AsyncMock) as mock_enqueue,
    ):
        response = await client.post(
            f"/api/v1/chats/{chat_id}/messages",
            headers=operator_a_headers,
            json={"text": "Hello outbound", "kind": "text", "idempotency_key": "evt-key-1"},
        )
        assert response.status_code == 202, response.text
        mock_publish.assert_awaited_once()
        topic, payload = mock_publish.await_args.args[0], mock_publish.await_args.args[1]
        assert topic == "chat.message.outbound.requested"
        assert payload["chat_id"] == chat_id
        message_id = response.json()["id"]
        assert payload["message_id"] == message_id

        engine = create_engine(_sync_database_url(test_settings.database_url))
        try:
            with engine.begin() as connection:
                row = connection.execute(
                    text(
                        """
                        SELECT id, command, payload
                        FROM bot_outbound_log
                        WHERE (payload->>'internal_id')::bigint = :message_id
                        ORDER BY id DESC
                        LIMIT 1
                        """
                    ),
                    {"message_id": message_id},
                ).mappings().one_or_none()
        finally:
            engine.dispose()

        assert row is not None
        assert row["command"] == "send_message"
        assert row["payload"]["contact"]["telegram_user_id"] == telegram_user_id
        assert row["payload"]["message"]["text"] == "Hello outbound"
        assert row["payload"]["reply_to_external_id"] is None
        mock_enqueue.assert_awaited_once()
        args, kwargs = mock_enqueue.await_args
        assert args[0] == "dispatch_outbound"
        assert args[1]["outbound_log_id"] == row["id"]
        assert kwargs.get("delay_seconds", 0) == 0
