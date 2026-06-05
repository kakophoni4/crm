# ruff: noqa: RUF001 — Cyrillic literals required for Russian FTS tests.
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine, text

from app.shared.settings import Settings
from tests.auth.conftest import _sync_database_url


@pytest.mark.asyncio
async def test_search_finds_russian_word(
    client: AsyncClient,
    db_ready: None,
    chats_org: dict[str, object],
    operator_a_headers: dict[str, str],
    test_settings: Settings,
) -> None:
    chat_id = chats_org["chat_ids"]["a"]
    assert isinstance(chat_id, int)
    unique_word = "согласованность"

    engine = create_engine(_sync_database_url(test_settings.database_url))
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO messages (chat_id, direction, kind, text)
                VALUES (:chat_id, 'inbound', 'text', :body)
                """
            ),
            {"chat_id": chat_id, "body": f"Договорились о {unique_word} поставки"},
        )
    engine.dispose()

    response = await client.get(
        "/api/v1/chats/search",
        headers=operator_a_headers,
        params={"q": unique_word, "scope": "group"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert any(item["message_id"] for item in body["items"])
    assert any(unique_word in item["snippet"].lower() for item in body["items"])
    for item in body["items"]:
        assert "lead_id" in item


@pytest.mark.asyncio
async def test_search_not_visible_outside_group_scope(
    client: AsyncClient,
    db_ready: None,
    chats_org: dict[str, object],
    operator_a_headers: dict[str, str],
    test_settings: Settings,
) -> None:
    chat_id = chats_org["chat_ids"]["dept_b"]
    assert isinstance(chat_id, int)
    secret_word = "инкогнитоотдел"

    engine = create_engine(_sync_database_url(test_settings.database_url))
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO messages (chat_id, direction, kind, text)
                VALUES (:chat_id, 'inbound', 'text', :body)
                """
            ),
            {"chat_id": chat_id, "body": f"Секретное слово {secret_word} только для отдела B"},
        )
    engine.dispose()

    response = await client.get(
        "/api/v1/chats/search",
        headers=operator_a_headers,
        params={"q": secret_word, "scope": "group"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["items"] == []


@pytest.mark.asyncio
async def test_search_short_query_returns_422(
    client: AsyncClient,
    db_ready: None,
    operator_a_headers: dict[str, str],
) -> None:
    response = await client.get(
        "/api/v1/chats/search",
        headers=operator_a_headers,
        params={"q": "а"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_search_cursor_pagination(
    client: AsyncClient,
    db_ready: None,
    chats_org: dict[str, object],
    operator_a_headers: dict[str, str],
    test_settings: Settings,
) -> None:
    chat_id = chats_org["chat_ids"]["a"]
    assert isinstance(chat_id, int)
    marker = "пагинацияfts"

    engine = create_engine(_sync_database_url(test_settings.database_url))
    with engine.begin() as connection:
        for idx in range(3):
            connection.execute(
                text(
                    """
                    INSERT INTO messages (chat_id, direction, kind, text, created_at)
                    VALUES (
                        :chat_id, 'inbound', 'text', :body,
                        now() - (:offset * interval '1 second')
                    )
                    """
                ),
                {
                    "chat_id": chat_id,
                    "body": f"{marker} сообщение {idx}",
                    "offset": 3 - idx,
                },
            )
    engine.dispose()

    first = await client.get(
        "/api/v1/chats/search",
        headers=operator_a_headers,
        params={"q": marker, "scope": "group", "limit": 2},
    )
    assert first.status_code == 200, first.text
    first_body = first.json()
    assert len(first_body["items"]) == 2
    assert first_body["next_cursor"] is not None

    second = await client.get(
        "/api/v1/chats/search",
        headers=operator_a_headers,
        params={
            "q": marker,
            "scope": "group",
            "limit": 2,
            "cursor": first_body["next_cursor"],
        },
    )
    assert second.status_code == 200, second.text
    second_body = second.json()
    assert len(second_body["items"]) >= 1

    first_ids = {item["message_id"] for item in first_body["items"]}
    second_ids = {item["message_id"] for item in second_body["items"]}
    assert first_ids.isdisjoint(second_ids)
