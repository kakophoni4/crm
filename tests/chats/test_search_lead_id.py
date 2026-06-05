# ruff: noqa: RUF001
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine, text

from app.shared.settings import Settings
from tests.auth.conftest import _sync_database_url


@pytest.mark.asyncio
async def test_search_message_includes_lead_id(
    client: AsyncClient,
    db_ready: None,
    chats_org: dict[str, object],
    operator_a_headers: dict[str, str],
    test_settings: Settings,
) -> None:
    chat_id = chats_org["chat_ids"]["a"]
    assert isinstance(chat_id, int)
    marker = "лидпоискмаркер"

    engine = create_engine(_sync_database_url(test_settings.database_url))
    with engine.begin() as connection:
        lead_id = connection.execute(
            text("SELECT current_lead_id FROM chats WHERE id = :cid"),
            {"cid": chat_id},
        ).scalar_one()
        connection.execute(
            text(
                """
                INSERT INTO messages (chat_id, lead_id, direction, kind, text)
                VALUES (:chat_id, :lead_id, 'inbound', 'text', :body)
                """
            ),
            {
                "chat_id": chat_id,
                "lead_id": lead_id,
                "body": f"Текст с {marker} для поиска",
            },
        )
    engine.dispose()

    response = await client.get(
        "/api/v1/chats/search",
        headers=operator_a_headers,
        params={"q": marker, "scope": "group"},
    )
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert len(items) >= 1
    hit = next(item for item in items if marker in item["snippet"].lower())
    if lead_id is not None:
        assert hit["lead_id"] == lead_id
