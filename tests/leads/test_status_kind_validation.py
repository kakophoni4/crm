from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine, text

from app.shared.settings import Settings
from tests.auth.conftest import _sync_database_url
from tests.chats.conftest import login


@pytest.mark.asyncio
async def test_list_chats_status_id_rejects_lead_pipeline(
    client: AsyncClient,
    leads_api_org: dict[str, object],
    db_ready: None,
) -> None:
    emails = leads_api_org["emails"]
    assert isinstance(emails, dict)
    token = await login(client, str(emails["op_a"]), str(leads_api_org["password"]))
    response = await client.get(
        "/api/v1/chats",
        headers={"Authorization": f"Bearer {token}"},
        params={"status_id": leads_api_org["pipeline_new"]},
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "validation_error"
    assert "chat_label" in response.json()["error"]["message"]


@pytest.mark.asyncio
async def test_patch_chat_status_id_rejects_lead_pipeline(
    client: AsyncClient,
    leads_api_org: dict[str, object],
    db_ready: None,
) -> None:
    emails = leads_api_org["emails"]
    assert isinstance(emails, dict)
    chat_ids = leads_api_org["chat_ids"]
    assert isinstance(chat_ids, dict)
    token = await login(client, str(emails["op_a"]), str(leads_api_org["password"]))
    response = await client.patch(
        f"/api/v1/chats/{chat_ids['a']}/status_id",
        headers={"Authorization": f"Bearer {token}"},
        json={"status_id": leads_api_org["pipeline_new"]},
    )
    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "permission_denied"
    assert "updated automatically" in response.json()["error"]["message"]


@pytest.mark.asyncio
async def test_patch_lead_rejects_chat_label_status(
    client: AsyncClient,
    leads_api_org: dict[str, object],
    test_settings: Settings,
    db_ready: None,
) -> None:
    emails = leads_api_org["emails"]
    assert isinstance(emails, dict)
    lead_ids = leads_api_org["lead_ids"]
    assert isinstance(lead_ids, dict)
    token = await login(client, str(emails["op_a"]), str(leads_api_org["password"]))

    engine = create_engine(_sync_database_url(test_settings.database_url))
    try:
        with engine.begin() as conn:
            chat_label_id = conn.execute(
                text(
                    """
                    SELECT id FROM statuses
                    WHERE code = 'client_new' AND kind = 'chat_label'
                    LIMIT 1
                    """
                ),
            ).scalar_one()
    finally:
        engine.dispose()

    response = await client.patch(
        f"/api/v1/leads/{lead_ids['open_a']}",
        headers={"Authorization": f"Bearer {token}"},
        json={"status_id": int(chat_label_id)},
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "validation_error"
    assert "lead_pipeline" in response.json()["error"]["message"]


@pytest.mark.asyncio
async def test_create_status_chat_label_and_list_filter(
    client: AsyncClient,
    db_ready: None,
    admin_headers: dict[str, str],
) -> None:
    create = await client.post(
        "/api/v1/statuses",
        headers=admin_headers,
        json={
            "code": "vip_client",
            "kind": "chat_label",
            "label": "VIP клиент",
            "color": "#FFD700",
            "sort_order": 20,
        },
    )
    assert create.status_code == 201, create.text
    body = create.json()
    assert body["kind"] == "chat_label"
    assert body["code"] == "vip_client"

    listing = await client.get(
        "/api/v1/statuses",
        headers=admin_headers,
        params={"kind": "chat_label"},
    )
    assert listing.status_code == 200, listing.text
    codes = {item["code"] for item in listing.json()["items"]}
    assert "vip_client" in codes
    assert all(item["kind"] == "chat_label" for item in listing.json()["items"])


@pytest.mark.asyncio
async def test_create_manual_lead_rejects_chat_label_status(
    client: AsyncClient,
    leads_api_org: dict[str, object],
    test_settings: Settings,
    db_ready: None,
) -> None:
    emails = leads_api_org["emails"]
    assert isinstance(emails, dict)
    lead_ids = leads_api_org["lead_ids"]
    assert isinstance(lead_ids, dict)
    token = await login(client, str(emails["op_a"]), str(leads_api_org["password"]))
    contact_id = leads_api_org["contact_id"]

    await client.post(
        f"/api/v1/leads/{lead_ids['open_a']}/close",
        headers={"Authorization": f"Bearer {token}"},
        json={"status_id": leads_api_org["pipeline_won"]},
    )

    engine = create_engine(_sync_database_url(test_settings.database_url))
    try:
        with engine.begin() as conn:
            chat_label_id = conn.execute(
                text(
                    """
                    SELECT id FROM statuses
                    WHERE code = 'client_new' AND kind = 'chat_label'
                    LIMIT 1
                    """
                ),
            ).scalar_one()
    finally:
        engine.dispose()

    response = await client.post(
        f"/api/v1/contacts/{contact_id}/leads",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "group_id": leads_api_org["group_a"],
            "status_id": int(chat_label_id),
        },
    )
    assert response.status_code == 422, response.text
    assert "lead_pipeline" in response.json()["error"]["message"]
