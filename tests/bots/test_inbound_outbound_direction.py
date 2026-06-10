from __future__ import annotations

from unittest.mock import AsyncMock, patch

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
    telegram_user_id: int = 999001,
) -> None:
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
    assert response.json()["status"] == "accepted"
    await process_bot_event("process_bot_event", {"event_id": event_id})


@pytest.mark.asyncio
async def test_outbound_direction_creates_outbound_message(
    client: AsyncClient,
    db_ready: None,
    test_settings,
    bots_org: dict[str, object],
) -> None:
    del bots_org
    event_id = "01J5OUTBOUND001"
    await _accept_and_process(
        client,
        event_id=event_id,
        direction="outbound",
        external_id="msg_out_001",
        text="Reply from Telegram",
    )

    engine = create_engine(_sync_database_url(test_settings.database_url))
    try:
        with engine.connect() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT direction, sender_user_id, text
                    FROM messages
                    WHERE external_message_id = :ext
                    """
                ),
                {"ext": "msg_out_001"},
            ).one()
    finally:
        engine.dispose()

    assert str(row[0]) == "outbound"
    assert row[1] is None
    assert row[2] == "Reply from Telegram"


@pytest.mark.asyncio
async def test_outbound_direction_idempotent_by_external_id(
    client: AsyncClient,
    db_ready: None,
    test_settings,
    bots_org: dict[str, object],
) -> None:
    del bots_org
    await _accept_and_process(
        client,
        event_id="01J5OUTBOUND002",
        direction="outbound",
        external_id="msg_out_dup",
        text="Once",
    )
    await _accept_and_process(
        client,
        event_id="01J5OUTBOUND003",
        direction="outbound",
        external_id="msg_out_dup",
        text="Once",
    )

    engine = create_engine(_sync_database_url(test_settings.database_url))
    try:
        with engine.connect() as connection:
            count = connection.execute(
                text(
                    """
                    SELECT COUNT(*) FROM messages
                    WHERE external_message_id = :ext
                    """
                ),
                {"ext": "msg_out_dup"},
            ).scalar_one()
    finally:
        engine.dispose()

    assert count == 1


@pytest.mark.asyncio
async def test_inbound_without_direction_unchanged(
    client: AsyncClient,
    db_ready: None,
    test_settings,
    bots_org: dict[str, object],
) -> None:
    del bots_org
    event_id = "01J5INBOUND001"
    await _accept_and_process(
        client,
        event_id=event_id,
        external_id="msg_in_dir_001",
        text="Client hello",
        telegram_user_id=999002,
    )

    engine = create_engine(_sync_database_url(test_settings.database_url))
    try:
        with engine.connect() as connection:
            direction = connection.execute(
                text(
                    """
                    SELECT direction FROM messages
                    WHERE external_message_id = :ext
                    """
                ),
                {"ext": "msg_in_dir_001"},
            ).scalar_one()
    finally:
        engine.dispose()

    assert str(direction) == "inbound"
