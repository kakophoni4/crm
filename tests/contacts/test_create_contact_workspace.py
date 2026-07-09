from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine, text

from app.shared.settings import Settings
from tests.auth.conftest import _sync_database_url


@pytest.mark.asyncio
async def test_create_contact_open_workspace_creates_chat_and_lead(
    client: AsyncClient,
    ownership_op1_headers: dict[str, str],
    ownership_org: dict[str, object],
    test_settings: Settings,
    db_ready: None,
) -> None:
    del db_ready
    response = await client.post(
        "/api/v1/contacts",
        headers={**ownership_op1_headers, "X-Request-Id": "test-workspace-01"},
        json={
            "full_name": "Offline Workspace Contact",
            "phone": "+79003334455",
            "source": "manual",
            "open_workspace": True,
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    contact_id = body["id"]
    workspace = body["workspace"]
    assert workspace is not None
    assert workspace["created_chat"] is True
    assert workspace["created_lead"] is True

    group_id = int(ownership_org["group_id"])
    engine = create_engine(_sync_database_url(test_settings.database_url))
    try:
        with engine.connect() as conn:
            chat_row = conn.execute(
                text(
                    """
                    SELECT id, current_lead_id
                    FROM chats
                    WHERE contact_id = :cid
                      AND bot_id IS NULL
                      AND assigned_group_id = :gid
                      AND status != 'archived'
                    """
                ),
                {"cid": contact_id, "gid": group_id},
            ).one()
            lead_row = conn.execute(
                text(
                    """
                    SELECT id, chat_id, bot_id
                    FROM leads
                    WHERE id = :lead_id
                    """
                ),
                {"lead_id": workspace["lead_id"]},
            ).one()
    finally:
        engine.dispose()

    assert int(chat_row.id) == workspace["chat_id"]
    assert int(chat_row.current_lead_id) == workspace["lead_id"]
    assert int(lead_row.chat_id) == workspace["chat_id"]
    assert lead_row.bot_id is None


@pytest.mark.asyncio
async def test_create_contact_open_workspace_admin_requires_group_or_workspace_group_id(
    client: AsyncClient,
    admin_headers: dict[str, str],
    ownership_org: dict[str, object],
    db_ready: None,
) -> None:
    del db_ready
    group_id = int(ownership_org["group_id"])
    response = await client.post(
        "/api/v1/contacts",
        headers={**admin_headers, "X-Request-Id": "test-workspace-admin"},
        json={
            "full_name": "Admin Offline Contact",
            "source": "manual",
            "open_workspace": True,
            "workspace_group_id": group_id,
        },
    )
    assert response.status_code == 201, response.text
    workspace = response.json()["workspace"]
    assert workspace is not None
    assert workspace["group_id"] == group_id
