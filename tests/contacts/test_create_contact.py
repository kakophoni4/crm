from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine, text

from app.shared.settings import Settings
from tests.auth.conftest import _sync_database_url


@pytest.mark.asyncio
async def test_create_contact_as_admin(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    response = await client.post(
        "/api/v1/contacts",
        headers={**admin_headers, "X-Request-Id": "test-create-contact-01"},
        json={
            "full_name": "New Contact",
            "phone": "+79001234567",
            "email": "new@example.com",
            "telegram_user_id": 100001,
            "telegram_username": "new_contact",
            "custom_fields": {"city": "Moscow"},
            "source": "manual",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["full_name"] == "New Contact"
    assert body["custom_fields"]["city"] == "Moscow"
    assert body["status"] == "new"
    assert body["telegram_user_id"] == 100001


@pytest.mark.asyncio
async def test_create_contact_as_operator_visible_in_list(
    client: AsyncClient,
    ownership_op1_headers: dict[str, str],
    ownership_org: dict[str, object],
    test_settings: Settings,
    db_ready: None,
) -> None:
    del db_ready
    response = await client.post(
        "/api/v1/contacts",
        headers={**ownership_op1_headers, "X-Request-Id": "test-create-contact-op1"},
        json={
            "full_name": "Operator Manual Contact",
            "phone": "+79001112233",
            "source": "manual",
            "open_workspace": True,
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    contact_id = body["id"]
    workspace = body.get("workspace")
    assert workspace is not None
    assert workspace["chat_id"] > 0
    assert workspace["lead_id"] > 0
    assert workspace["created_chat"] is True
    assert workspace["created_lead"] is True

    detail = await client.get(
        f"/api/v1/contacts/{contact_id}",
        headers=ownership_op1_headers,
    )
    assert detail.status_code == 200, detail.text

    listing = await client.get("/api/v1/contacts", headers=ownership_op1_headers)
    assert listing.status_code == 200, listing.text
    ids = {item["id"] for item in listing.json()["items"]}
    assert contact_id in ids

    group_id = int(ownership_org["group_id"])
    user_ids = ownership_org["user_ids"]
    assert isinstance(user_ids, dict)
    op1_id = user_ids["owner.op1@crm.local"]

    engine = create_engine(_sync_database_url(test_settings.database_url))
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT owner_user_id, assignment_source
                    FROM contact_group_assignments
                    WHERE contact_id = :cid AND group_id = :gid
                    """
                ),
                {"cid": contact_id, "gid": group_id},
            ).one()
    finally:
        engine.dispose()

    assert int(row.owner_user_id) == int(op1_id)
    assert row.assignment_source == "manual_create"
