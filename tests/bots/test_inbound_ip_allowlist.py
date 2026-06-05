from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine, text

from tests.auth.conftest import _sync_database_url
from tests.bots.conftest import build_inbound_payload


@pytest.mark.asyncio
async def test_ip_not_in_allowlist_returns_401(
    client: AsyncClient,
    db_ready: None,
    test_settings,
    bots_org: dict[str, object],
) -> None:
    engine = create_engine(_sync_database_url(test_settings.database_url))
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    UPDATE bots
                    SET ip_allowlist = ARRAY['203.0.113.1'::inet]
                    WHERE code = 'test_bot_a'
                    """
                ),
            )
    finally:
        engine.dispose()

    body, headers = build_inbound_payload(event_id="01J5IPBLOCK0001")
    response = await client.post("/api/v1/bot-events", content=body, headers=headers)
    assert response.status_code == 401

    engine = create_engine(_sync_database_url(test_settings.database_url))
    try:
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE bots SET ip_allowlist = NULL WHERE code = 'test_bot_a'"),
            )
    finally:
        engine.dispose()
