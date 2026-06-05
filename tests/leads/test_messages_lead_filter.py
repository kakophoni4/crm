from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine, text

from app.shared.settings import Settings
from tests.auth.conftest import _sync_database_url
from tests.chats.conftest import login


@pytest.mark.asyncio
async def test_list_messages_filter_by_lead_id(
    client: AsyncClient,
    leads_api_org: dict[str, object],
    test_settings: Settings,
    db_ready: None,
) -> None:
    del db_ready
    lead_ids = leads_api_org["lead_ids"]
    chat_ids = leads_api_org["chat_ids"]
    assert isinstance(lead_ids, dict)
    assert isinstance(chat_ids, dict)
    open_lead_id = int(lead_ids["open_a"])
    closed_lead_id = int(lead_ids["closed_a"])
    chat_id = int(chat_ids["a"])

    engine = create_engine(_sync_database_url(test_settings.database_url))
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO messages (chat_id, lead_id, direction, kind, text)
                    VALUES
                        (:cid, :open_lid, 'inbound', 'text', 'open lead msg'),
                        (:cid, :closed_lid, 'inbound', 'text', 'closed lead msg')
                    """
                ),
                {
                    "cid": chat_id,
                    "open_lid": open_lead_id,
                    "closed_lid": closed_lead_id,
                },
            )
    finally:
        engine.dispose()

    token = await login(
        client,
        str(leads_api_org["emails"]["op_a"]),
        str(leads_api_org["password"]),
    )
    headers = {"Authorization": f"Bearer {token}"}

    filtered = await client.get(
        f"/api/v1/chats/{chat_id}/messages",
        headers=headers,
        params={"lead_id": open_lead_id},
    )
    assert filtered.status_code == 200, filtered.text
    items = filtered.json()["items"]
    assert len(items) >= 1
    assert all(item["lead_id"] == open_lead_id for item in items)
    assert not any(item["lead_id"] == closed_lead_id for item in items)

    all_msgs = await client.get(f"/api/v1/chats/{chat_id}/messages", headers=headers)
    assert all_msgs.status_code == 200
    all_lead_ids = {item["lead_id"] for item in all_msgs.json()["items"]}
    assert open_lead_id in all_lead_ids
    assert closed_lead_id in all_lead_ids


@pytest.mark.asyncio
async def test_list_messages_foreign_lead_returns_404(
    client: AsyncClient,
    leads_api_org: dict[str, object],
    db_ready: None,
) -> None:
    del db_ready
    lead_ids = leads_api_org["lead_ids"]
    chat_ids = leads_api_org["chat_ids"]
    assert isinstance(lead_ids, dict)
    foreign_lead_id = int(lead_ids["closed_b"])
    chat_id = int(chat_ids["a"])

    token = await login(
        client,
        str(leads_api_org["emails"]["op_a"]),
        str(leads_api_org["password"]),
    )
    response = await client.get(
        f"/api/v1/chats/{chat_id}/messages",
        headers={"Authorization": f"Bearer {token}"},
        params={"lead_id": foreign_lead_id},
    )
    assert response.status_code == 404
