from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine, text

from app.shared.settings import Settings
from tests.auth.conftest import _sync_database_url
from tests.chats.conftest import login


@pytest.mark.asyncio
async def test_senior_can_patch_lead_when_not_card_owner(
    client: AsyncClient,
    leads_api_org: dict[str, object],
    test_settings: Settings,
    db_ready: None,
) -> None:
    emails = leads_api_org["emails"]
    assert isinstance(emails, dict)
    senior_token = await login(client, str(emails["senior"]), str(leads_api_org["password"]))
    op_token = await login(client, str(emails["op_a"]), str(leads_api_org["password"]))
    contact_id = leads_api_org["contact_id"]
    group_a = leads_api_org["group_a"]
    lead_ids = leads_api_org["lead_ids"]
    assert isinstance(lead_ids, dict)
    open_lead_id = lead_ids["open_a"]

    engine = create_engine(_sync_database_url(test_settings.database_url))
    try:
        with engine.begin() as conn:
            op_a_id = conn.execute(
                text("SELECT id FROM users WHERE email = :email"),
                {"email": emails["op_a"]},
            ).scalar_one()
            conn.execute(
                text(
                    """
                    INSERT INTO contact_group_assignments (
                        contact_id, group_id, owner_user_id, assignment_source
                    )
                    VALUES (:cid, :gid, :owner, 'manual_transfer')
                    ON CONFLICT (contact_id, group_id) DO UPDATE
                    SET owner_user_id = EXCLUDED.owner_user_id
                    """
                ),
                {"cid": contact_id, "gid": group_a, "owner": op_a_id},
            )
            in_progress_id = conn.execute(
                text(
                    """
                    SELECT id FROM statuses
                    WHERE code = 'in_progress' AND kind = 'lead_pipeline'
                    LIMIT 1
                    """
                ),
            ).scalar_one()
    finally:
        engine.dispose()

    chat_resp = await client.get(
        f"/api/v1/chats",
        headers={"Authorization": f"Bearer {senior_token}"},
        params={"contact_id": contact_id, "limit": 10},
    )
    assert chat_resp.status_code == 200, chat_resp.text
    chat_items = chat_resp.json()["items"]
    assert chat_items, "senior should see department chat"
    current_lead = chat_items[0].get("current_lead")
    assert current_lead is not None
    assert current_lead.get("label"), "senior should see lead pipeline label in scope"
    assert current_lead["id"] == open_lead_id

    patch_resp = await client.patch(
        f"/api/v1/leads/{open_lead_id}",
        headers={"Authorization": f"Bearer {senior_token}"},
        json={"status_id": int(in_progress_id)},
    )
    assert patch_resp.status_code == 200, patch_resp.text
    assert patch_resp.json()["status_id"] == int(in_progress_id)

    op_patch = await client.patch(
        f"/api/v1/leads/{open_lead_id}",
        headers={"Authorization": f"Bearer {op_token}"},
        json={"status_id": int(leads_api_org["pipeline_new"])},
    )
    assert op_patch.status_code == 200, op_patch.text
