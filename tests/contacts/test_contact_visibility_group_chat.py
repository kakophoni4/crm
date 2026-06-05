from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine, text

from app.shared.settings import Settings
from tests.auth.conftest import _sync_database_url
from tests.contacts.conftest_ownership import _login_ownership


@pytest.mark.asyncio
async def test_user_sees_contact_via_group_chat_without_assigned_user(
    client: AsyncClient,
    ownership_org: dict[str, object],
    test_settings: Settings,
    db_ready: None,
) -> None:
    """USER + ownership_v2: chat in group G is enough without contact.assigned_user_id."""
    group_id = int(ownership_org["group_id"])
    dept_id = int(ownership_org["dept_id"])
    user_ids = ownership_org["user_ids"]
    emails = ownership_org["emails"]
    assert isinstance(user_ids, dict)
    assert isinstance(emails, dict)
    senior_id = user_ids["owner.senior@crm.local"]

    engine = create_engine(_sync_database_url(test_settings.database_url))
    with engine.begin() as conn:
        contact_id = conn.execute(
            text(
                """
                INSERT INTO contacts (full_name, created_by, assigned_department_id)
                VALUES ('Group Chat Visible Contact', :created_by, :dept_id)
                RETURNING id
                """
            ),
            {"created_by": senior_id, "dept_id": dept_id},
        ).scalar_one()
        conn.execute(
            text(
                """
                INSERT INTO chats (
                    contact_id, assigned_group_id, assigned_department_id,
                    status, last_message_at, last_message_preview
                )
                VALUES (
                    :cid, :gid, :dept_id, 'open', now(), 'group visibility probe'
                )
                """
            ),
            {"cid": contact_id, "gid": group_id, "dept_id": dept_id},
        )
    engine.dispose()

    token = await _login_ownership(client, str(emails["op1"]), str(ownership_org["password"]))
    headers = {"Authorization": f"Bearer {token}"}

    detail = await client.get(f"/api/v1/contacts/{contact_id}", headers=headers)
    assert detail.status_code == 200, detail.text

    audit = await client.get(
        f"/api/v1/contacts/{contact_id}/groups/{group_id}/reply-audit",
        headers=headers,
        params={"limit": 10},
    )
    assert audit.status_code == 200, audit.text
    assert audit.json()["items"] == []
