from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine, text

from app.modules.search.rate_limit import reset_in_memory_rate_limits
from app.shared.settings import Settings, get_settings
from tests.auth.conftest import _sync_database_url


@pytest.mark.asyncio
async def test_global_search_messages_respects_chat_scope(
    client: AsyncClient,
    db_ready: None,
    chats_org: dict[str, object],
    operator_a_headers: dict[str, str],
    test_settings: Settings,
) -> None:
    chat_id = chats_org["chat_ids"]["dept_b"]
    assert isinstance(chat_id, int)
    secret_word = "глобалинкогнито"

    engine = create_engine(_sync_database_url(test_settings.database_url))
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO messages (chat_id, direction, kind, text)
                VALUES (:chat_id, 'inbound', 'text', :body)
                """
            ),
            {"chat_id": chat_id, "body": f"Секрет {secret_word} в другом отделе"},
        )
    engine.dispose()

    response = await client.get(
        "/api/v1/search",
        headers=operator_a_headers,
        params={"q": secret_word, "types": "messages"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["messages"]["items"] == []


@pytest.mark.asyncio
async def test_global_search_chats_respects_group_scope(
    client: AsyncClient,
    db_ready: None,
    chats_org: dict[str, object],
    operator_a_headers: dict[str, str],
) -> None:
    response = await client.get(
        "/api/v1/search",
        headers=operator_a_headers,
        params={"q": "DeptB", "types": "chats"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["chats"]["items"] == []


@pytest.mark.asyncio
async def test_global_search_contacts_respects_user_scope(
    client: AsyncClient,
    db_ready: None,
    chats_org: dict[str, object],
    operator_a_headers: dict[str, str],
) -> None:
    response = await client.get(
        "/api/v1/search",
        headers=operator_a_headers,
        params={"q": "DeptB", "types": "contacts"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["contacts"]["items"] == []


@pytest.mark.asyncio
async def test_global_search_finds_contact_and_message_by_ivan(
    client: AsyncClient,
    db_ready: None,
    chats_org: dict[str, object],
    operator_a_headers: dict[str, str],
    test_settings: Settings,
) -> None:
    chat_id = chats_org["chat_ids"]["a"]
    contact_id = chats_org["contact_ids"]["a"]
    assert isinstance(chat_id, int)
    assert isinstance(contact_id, int)

    engine = create_engine(_sync_database_url(test_settings.database_url))
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE contacts SET full_name = :name WHERE id = :id"),
            {"name": "Иван Петров", "id": contact_id},
        )
        connection.execute(
            text(
                """
                INSERT INTO messages (chat_id, direction, kind, text)
                VALUES (:chat_id, 'inbound', 'text', :body)
                """
            ),
            {"chat_id": chat_id, "body": "Иван уточнил условия договора"},
        )
    engine.dispose()

    response = await client.get(
        "/api/v1/search",
        headers=operator_a_headers,
        params={"q": "иван"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    contact_names = {item["full_name"] for item in body["contacts"]["items"]}
    assert "Иван Петров" in contact_names
    assert any(item["chat_id"] == chat_id for item in body["messages"]["items"])


@pytest.mark.asyncio
async def test_global_search_finds_visible_chat_by_preview(
    client: AsyncClient,
    db_ready: None,
    chats_org: dict[str, object],
    operator_a_headers: dict[str, str],
) -> None:
    response = await client.get(
        "/api/v1/search",
        headers=operator_a_headers,
        params={"q": "Preview a", "types": "chats"},
    )
    assert response.status_code == 200, response.text
    chat_ids = {item["id"] for item in response.json()["chats"]["items"]}
    assert chats_org["chat_ids"]["a"] in chat_ids


@pytest.mark.asyncio
async def test_global_search_rate_limit_429(
    client: AsyncClient,
    db_ready: None,
    chats_org: dict[str, object],
    operator_a_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEARCH_RATE_LIMIT_PER_MINUTE", "3")
    monkeypatch.setenv("SEARCH_RATE_LIMIT_USE_REDIS", "false")
    get_settings.cache_clear()
    reset_in_memory_rate_limits()

    try:
        for _ in range(3):
            ok = await client.get(
                "/api/v1/search",
                headers=operator_a_headers,
                params={"q": "ab", "types": "contacts"},
            )
            assert ok.status_code == 200, ok.text

        limited = await client.get(
            "/api/v1/search",
            headers=operator_a_headers,
            params={"q": "ab", "types": "contacts"},
        )
        assert limited.status_code == 429, limited.text
        assert limited.json()["error"]["code"] == "rate_limited"
    finally:
        reset_in_memory_rate_limits()
        get_settings.cache_clear()
