from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine, text

from app.shared.settings import Settings
from tests.auth.conftest import _sync_database_url


@pytest.mark.asyncio
async def test_create_chat(
    client: AsyncClient,
    db_ready: None,
    chats_org: dict[str, object],
    operator_a_headers: dict[str, str],
    test_settings: Settings,
) -> None:
    user_ids = chats_org["user_ids"]
    assert isinstance(user_ids, dict)
    group_id = int(chats_org["group_a"])
    operator_id = user_ids["operator.chats.a@crm.local"]

    create_resp = await client.post(
        "/api/v1/contacts",
        headers=operator_a_headers,
        json={"full_name": "Manual Chat Contact"},
    )
    assert create_resp.status_code == 201, create_resp.text
    contact_id = create_resp.json()["id"]

    engine = create_engine(_sync_database_url(test_settings.database_url))
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO contact_group_assignments (
                    contact_id, group_id, owner_user_id, assignment_source
                )
                VALUES (:cid, :gid, :owner, 'migration')
                ON CONFLICT (contact_id, group_id) DO NOTHING
                """
            ),
            {"cid": contact_id, "gid": group_id, "owner": operator_id},
        )
    engine.dispose()

    response = await client.post(
        "/api/v1/chats",
        headers=operator_a_headers,
        json={"contact_id": contact_id},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["contact_id"] == contact_id
    assert body["status"] == "open"

    dup = await client.post(
        "/api/v1/chats",
        json={"contact_id": contact_id},
        headers=operator_a_headers,
    )
    assert dup.status_code == 409
