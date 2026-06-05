from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine, text

from app.modules.search.trgm import trgm_search_indexes_available
from app.shared.db import get_session_factory
from app.shared.settings import Settings
from tests.auth.conftest import _sync_database_url


@pytest.mark.asyncio
async def test_trgm_indexes_present_at_head(db_ready: None) -> None:
    del db_ready
    session_factory = get_session_factory()
    async with session_factory() as session:
        assert await trgm_search_indexes_available(session) is True


@pytest.mark.asyncio
async def test_global_search_contacts_uses_trgm_ranking(
    client: AsyncClient,
    db_ready: None,
    chats_org: dict[str, object],
    operator_a_headers: dict[str, str],
    test_settings: Settings,
) -> None:
    contact_id = chats_org["contact_ids"]["a"]
    assert isinstance(contact_id, int)
    unique = "тргмтестуник"

    engine = create_engine(_sync_database_url(test_settings.database_url))
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE contacts SET full_name = :name WHERE id = :id"),
            {"name": f"{unique} Петров", "id": contact_id},
        )
    engine.dispose()

    response = await client.get(
        "/api/v1/search",
        headers=operator_a_headers,
        params={"q": unique[:4], "types": "contacts"},
    )
    assert response.status_code == 200, response.text
    names = {item["full_name"] for item in response.json()["contacts"]["items"]}
    assert f"{unique} Петров" in names
