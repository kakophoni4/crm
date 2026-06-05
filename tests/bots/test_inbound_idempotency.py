from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine, text

from tests.auth.conftest import _sync_database_url
from tests.bots.conftest import build_inbound_payload


@pytest.mark.asyncio
async def test_duplicate_event_id_returns_202_without_double_insert(
    client: AsyncClient,
    db_ready: None,
    test_settings,
    bots_org: dict[str, object],
) -> None:
    event_id = "01J5IDEMPOTENT01"
    body, headers = build_inbound_payload(event_id=event_id)

    first = await client.post("/api/v1/bot-events", content=body, headers=headers)
    assert first.status_code == 202
    assert first.json()["status"] == "accepted"

    second = await client.post("/api/v1/bot-events", content=body, headers=headers)
    assert second.status_code == 202
    assert second.json()["status"] == "duplicate"

    engine = create_engine(_sync_database_url(test_settings.database_url))
    try:
        with engine.connect() as connection:
            count = connection.execute(
                text("SELECT COUNT(*) FROM bot_events_inbox WHERE event_id = :eid"),
                {"eid": event_id},
            ).scalar_one()
    finally:
        engine.dispose()
    assert count == 1
