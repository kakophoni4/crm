from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine, text

from app.shared.settings import Settings
from tests.auth.conftest import _sync_database_url
from tests.chats.conftest import login


@pytest.mark.asyncio
async def test_mark_chat_read_clears_unread_for_actor(
    client: AsyncClient,
    chats_org: dict[str, object],
    test_settings: Settings,
    db_ready: None,
) -> None:
    emails = chats_org["emails"]
    assert isinstance(emails, dict)
    token = await login(client, str(emails["operator_a"]), str(chats_org["password"]))
    chat_id = int(chats_org["chat_ids"]["a"])

    engine = create_engine(_sync_database_url(test_settings.database_url))
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO messages (chat_id, direction, kind, text)
                    VALUES (:cid, 'inbound', 'text', 'unread ping')
                    """
                ),
                {"cid": chat_id},
            )

        response = await client.post(
            f"/api/v1/chats/{chat_id}/read",
            headers={"Authorization": f"Bearer {token}"},
            json={},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["chat_id"] == chat_id
        assert body["last_read_message_id"] is not None
    finally:
        engine.dispose()

    listed = await client.get(
        "/api/v1/chats",
        headers={"Authorization": f"Bearer {token}"},
        params={"unread_only": True},
    )
    assert listed.status_code == 200
    ids = {item["id"] for item in listed.json()["items"]}
    assert chat_id not in ids

    listed_all = await client.get(
        "/api/v1/chats",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert listed_all.status_code == 200
    row = next(item for item in listed_all.json()["items"] if item["id"] == chat_id)
    assert row["unread_for_me"] is False
    assert "unread_count_user" not in row


@pytest.mark.asyncio
async def test_mark_chat_read_per_operator_unread_only(
    client: AsyncClient,
    chats_org: dict[str, object],
    test_settings: Settings,
    db_ready: None,
) -> None:
    emails = chats_org["emails"]
    assert isinstance(emails, dict)
    chat_id = int(chats_org["chat_ids"]["a"])

    engine = create_engine(_sync_database_url(test_settings.database_url))
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO messages (chat_id, direction, kind, text)
                VALUES (:cid, 'inbound', 'text', 'multi-op unread')
                """
            ),
            {"cid": chat_id},
        )
    engine.dispose()

    token_a = await login(client, str(emails["operator_a"]), str(chats_org["password"]))
    token_b = await login(client, str(emails["operator_b"]), str(chats_org["password"]))

    read_a = await client.post(
        f"/api/v1/chats/{chat_id}/read",
        headers={"Authorization": f"Bearer {token_a}"},
        json={},
    )
    assert read_a.status_code == 200

    unread_a = await client.get(
        "/api/v1/chats",
        headers={"Authorization": f"Bearer {token_a}"},
        params={"unread_only": True},
    )
    assert unread_a.status_code == 200
    assert chat_id not in {item["id"] for item in unread_a.json()["items"]}

    unread_b = await client.get(
        "/api/v1/chats",
        headers={"Authorization": f"Bearer {token_b}"},
        params={"unread_only": True},
    )
    assert unread_b.status_code == 200
    unread_b_items = unread_b.json()["items"]
    assert chat_id in {item["id"] for item in unread_b_items}
    row_b = next(item for item in unread_b_items if item["id"] == chat_id)
    assert row_b["unread_for_me"] is True
