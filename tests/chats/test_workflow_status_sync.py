from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine, text

from app.workers.bots.process_event import process_bot_event
from tests.auth.conftest import _sync_database_url
from tests.bots.conftest import build_inbound_payload


async def _accept_and_process(
    client: AsyncClient,
    *,
    event_id: str,
    direction: str | None = None,
    external_id: str,
    text: str,
    telegram_user_id: int = 999101,
) -> None:
    from unittest.mock import AsyncMock, patch

    body, headers = build_inbound_payload(
        event_id=event_id,
        direction=direction,
        external_id=external_id,
        text=text,
        telegram_user_id=telegram_user_id,
    )
    with patch("app.modules.bots.service.enqueue", new_callable=AsyncMock):
        response = await client.post("/api/v1/bot-events", content=body, headers=headers)
    assert response.status_code == 202, response.text
    await process_bot_event("process_bot_event", {"event_id": event_id})


def _chat_label_code(engine, *, external_message_id: str) -> str | None:
    with engine.connect() as connection:
        return connection.execute(
            text(
                """
                SELECT s.code
                FROM messages m
                JOIN chats c ON c.id = m.chat_id
                LEFT JOIN statuses s ON s.id = c.status_id
                WHERE m.external_message_id = :ext
                """
            ),
            {"ext": external_message_id},
        ).scalar_one_or_none()


@pytest.mark.asyncio
async def test_inbound_sets_waiting_workflow_label(
    client: AsyncClient,
    db_ready: None,
    test_settings,
    bots_org: dict[str, object],
) -> None:
    del bots_org
    await _accept_and_process(
        client,
        event_id="01J5WORKFLOWIN01",
        external_id="msg_workflow_in_01",
        text="Need help",
        telegram_user_id=999101,
    )

    engine = create_engine(_sync_database_url(test_settings.database_url))
    try:
        assert _chat_label_code(engine, external_message_id="msg_workflow_in_01") == "waiting"
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_outbound_sets_answered_workflow_label(
    client: AsyncClient,
    db_ready: None,
    test_settings,
    bots_org: dict[str, object],
) -> None:
    del bots_org
    await _accept_and_process(
        client,
        event_id="01J5WORKFLOWOUT01",
        direction="outbound",
        external_id="msg_workflow_out_01",
        text="We replied from Telegram",
        telegram_user_id=999103,
    )

    engine = create_engine(_sync_database_url(test_settings.database_url))
    try:
        assert _chat_label_code(engine, external_message_id="msg_workflow_out_01") == "answered"
    finally:
        engine.dispose()
