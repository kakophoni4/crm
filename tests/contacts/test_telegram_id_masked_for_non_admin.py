from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine, text

from app.shared.settings import Settings
from tests.auth.conftest import _sync_database_url


@pytest.mark.asyncio
async def test_operator_does_not_see_telegram_user_id(
    client: AsyncClient,
    admin_headers: dict[str, str],
    operator_a_headers: dict[str, str],
    contacts_org: dict[str, object],
    test_settings: Settings,
) -> None:
    user_ids = contacts_org["user_ids"]
    assert isinstance(user_ids, dict)
    operator_id = user_ids["operator.a@crm.local"]
    group_a = int(contacts_org["contacts_group_a"])

    create_resp = await client.post(
        "/api/v1/contacts",
        headers=admin_headers,
        json={
            "full_name": "TG Mask Test",
            "telegram_user_id": 42424242,
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    contact_id = create_resp.json()["id"]
    assert create_resp.json()["telegram_user_id"] == 42424242

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
            {"cid": contact_id, "gid": group_a, "owner": operator_id},
        )
    engine.dispose()

    admin_get = await client.get(f"/api/v1/contacts/{contact_id}", headers=admin_headers)
    assert admin_get.status_code == 200
    assert admin_get.json()["telegram_user_id"] == 42424242

    operator_get = await client.get(f"/api/v1/contacts/{contact_id}", headers=operator_a_headers)
    assert operator_get.status_code == 200
    assert "telegram_user_id" not in operator_get.json()

    operator_list = await client.get("/api/v1/contacts", headers=operator_a_headers)
    assert operator_list.status_code == 200
    for item in operator_list.json()["items"]:
        assert "telegram_user_id" not in item
