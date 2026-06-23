from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine, text

from app.shared.settings import Settings
from tests.auth.conftest import _sync_database_url
from tests.chats.conftest import login


@pytest.mark.asyncio
async def test_list_leads_scoped_to_group(
    client: AsyncClient,
    leads_api_org: dict[str, object],
    db_ready: None,
) -> None:
    emails = leads_api_org["emails"]
    assert isinstance(emails, dict)
    token = await login(client, str(emails["op_a"]), str(leads_api_org["password"]))
    contact_id = leads_api_org["contact_id"]
    response = await client.get(
        f"/api/v1/contacts/{contact_id}/leads",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    group_ids = {item["group_id"] for item in items}
    assert group_ids == {leads_api_org["group_a"]}
    titles = {item.get("title") for item in items}
    assert "Closed A" in titles
    assert "Open A" in titles
    assert "Closed B" not in titles


@pytest.mark.asyncio
async def test_contact_crm_summary_prior_count_all_groups(
    client: AsyncClient,
    leads_api_org: dict[str, object],
    db_ready: None,
) -> None:
    emails = leads_api_org["emails"]
    assert isinstance(emails, dict)
    token = await login(client, str(emails["op_a"]), str(leads_api_org["password"]))
    contact_id = leads_api_org["contact_id"]
    response = await client.get(
        f"/api/v1/contacts/{contact_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    summary = response.json()["crm_summary"]
    assert summary["prior_leads_count"] == 2
    assert summary["first_registered_at"] is not None


@pytest.mark.asyncio
async def test_get_lead_other_group_returns_404(
    client: AsyncClient,
    leads_api_org: dict[str, object],
    db_ready: None,
) -> None:
    emails = leads_api_org["emails"]
    assert isinstance(emails, dict)
    token = await login(client, str(emails["op_a"]), str(leads_api_org["password"]))
    lead_ids = leads_api_org["lead_ids"]
    assert isinstance(lead_ids, dict)
    response = await client.get(
        f"/api/v1/leads/{lead_ids['closed_b']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_manual_lead_and_close(
    client: AsyncClient,
    leads_api_org: dict[str, object],
    db_ready: None,
) -> None:
    emails = leads_api_org["emails"]
    assert isinstance(emails, dict)
    lead_ids = leads_api_org["lead_ids"]
    assert isinstance(lead_ids, dict)
    token = await login(client, str(emails["op_a"]), str(leads_api_org["password"]))
    contact_id = leads_api_org["contact_id"]

    close_resp = await client.post(
        f"/api/v1/leads/{lead_ids['open_a']}/close",
        headers={"Authorization": f"Bearer {token}"},
        json={"status_id": leads_api_org["pipeline_won"]},
    )
    assert close_resp.status_code == 200, close_resp.text

    create_resp = await client.post(
        f"/api/v1/contacts/{contact_id}/leads",
        headers={"Authorization": f"Bearer {token}"},
        json={"group_id": leads_api_org["group_a"]},
    )
    assert create_resp.status_code == 201, create_resp.text
    created_id = create_resp.json()["id"]

    repeat_resp = await client.post(
        f"/api/v1/contacts/{contact_id}/leads",
        headers={"Authorization": f"Bearer {token}"},
        json={"group_id": leads_api_org["group_a"]},
    )
    assert repeat_resp.status_code == 201, repeat_resp.text
    assert repeat_resp.json()["id"] != created_id

    title_resp = await client.post(
        f"/api/v1/contacts/{contact_id}/leads",
        headers={"Authorization": f"Bearer {token}"},
        json={"group_id": leads_api_org["group_a"], "title": "Manual cycle"},
    )
    assert title_resp.status_code == 422


@pytest.mark.asyncio
async def test_patch_lead_status(
    client: AsyncClient,
    leads_api_org: dict[str, object],
    test_settings: Settings,
    db_ready: None,
) -> None:
    emails = leads_api_org["emails"]
    assert isinstance(emails, dict)
    op_token = await login(client, str(emails["op_a"]), str(leads_api_org["password"]))
    contact_id = leads_api_org["contact_id"]

    engine = create_engine(_sync_database_url(test_settings.database_url))
    try:
        with engine.begin() as conn:
            in_progress_id = conn.execute(
                text(
                    """
                    SELECT id FROM statuses
                    WHERE code = 'in_progress' AND kind = 'lead_pipeline'
                    LIMIT 1
                    """
                ),
            ).scalar_one()
            conn.execute(
                text(
                    """
                    UPDATE leads
                    SET closed_at = now()
                    WHERE contact_id = :cid AND group_id = :gid AND closed_at IS NULL
                    """
                ),
                {"cid": contact_id, "gid": leads_api_org["group_a"]},
            )
            lead_id = conn.execute(
                text(
                    """
                    INSERT INTO leads (
                        contact_id, group_id, chat_id, status_id, title
                    )
                    SELECT :cid, :gid, c.id, :status_id, 'Patch me'
                    FROM chats c
                    WHERE c.contact_id = :cid AND c.assigned_group_id = :gid
                    LIMIT 1
                    RETURNING id
                    """
                ),
                {
                    "cid": contact_id,
                    "gid": leads_api_org["group_a"],
                    "status_id": leads_api_org["pipeline_new"],
                },
            ).scalar_one()
    finally:
        engine.dispose()

    response = await client.patch(
        f"/api/v1/leads/{lead_id}",
        headers={"Authorization": f"Bearer {op_token}"},
        json={
            "status_id": int(in_progress_id),
            "comment": "Нужен перезвон",
            "custom_fields": {"priority": "high"},
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status_id"] == int(in_progress_id)
    assert body["comment"] == "Нужен перезвон"
    assert body["comments"]
    assert body["comments"][-1]["body"] == "Нужен перезвон"
    assert body["custom_fields"]["priority"] == "high"


@pytest.mark.asyncio
async def test_patch_lead_comment_only_is_persisted(
    client: AsyncClient,
    leads_api_org: dict[str, object],
    test_settings: Settings,
    db_ready: None,
) -> None:
    emails = leads_api_org["emails"]
    assert isinstance(emails, dict)
    op_token = await login(client, str(emails["op_a"]), str(leads_api_org["password"]))
    contact_id = leads_api_org["contact_id"]

    engine = create_engine(_sync_database_url(test_settings.database_url))
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE leads
                    SET closed_at = now()
                    WHERE contact_id = :cid AND group_id = :gid AND closed_at IS NULL
                    """
                ),
                {"cid": contact_id, "gid": leads_api_org["group_a"]},
            )
            lead_id = conn.execute(
                text(
                    """
                    INSERT INTO leads (contact_id, group_id, chat_id, status_id, title)
                    SELECT :cid, :gid, c.id, :status_id, 'Comment me'
                    FROM chats c
                    WHERE c.contact_id = :cid AND c.assigned_group_id = :gid
                    LIMIT 1
                    RETURNING id
                    """
                ),
                {
                    "cid": contact_id,
                    "gid": leads_api_org["group_a"],
                    "status_id": leads_api_org["pipeline_new"],
                },
            ).scalar_one()
    finally:
        engine.dispose()

    response = await client.patch(
        f"/api/v1/leads/{lead_id}",
        headers={"Authorization": f"Bearer {op_token}"},
        json={"comment": "Комментарий из чата"},
    )
    assert response.status_code == 200, response.text

    engine = create_engine(_sync_database_url(test_settings.database_url))
    try:
        with engine.begin() as conn:
            count = conn.execute(
                text("SELECT COUNT(*) FROM lead_comments WHERE lead_id = :lid"),
                {"lid": lead_id},
            ).scalar_one()
            assert int(count) == 1
    finally:
        engine.dispose()

    listed = await client.get(
        f"/api/v1/contacts/{contact_id}/leads",
        headers={"Authorization": f"Bearer {op_token}"},
    )
    assert listed.status_code == 200, listed.text
    row = next(item for item in listed.json()["items"] if item["id"] == lead_id)
    assert row["comments"][-1]["body"] == "Комментарий из чата"


@pytest.mark.asyncio
async def test_chats_filter_by_lead_open_only(
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
        params={"lead_open_only": True, "contact_id": leads_api_org["contact_id"]},
    )
    assert response.status_code == 200, response.text
    for item in response.json()["items"]:
        assert item["current_lead"] is not None
        assert item["current_lead"]["closed_at"] is None


@pytest.mark.asyncio
async def test_chats_include_current_lead_and_chat_label(
    client: AsyncClient,
    leads_api_org: dict[str, object],
    db_ready: None,
) -> None:
    emails = leads_api_org["emails"]
    assert isinstance(emails, dict)
    lead_ids = leads_api_org["lead_ids"]
    assert isinstance(lead_ids, dict)
    chat_ids = leads_api_org["chat_ids"]
    assert isinstance(chat_ids, dict)
    token = await login(client, str(emails["op_a"]), str(leads_api_org["password"]))
    response = await client.get(
        f"/api/v1/chats/{chat_ids['a']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["current_lead"] is not None
    assert body["current_lead"]["id"] == lead_ids["open_a"]
    assert body["current_lead"]["label"]


@pytest.mark.asyncio
async def test_patch_lead_rejects_oversized_payload(
    client: AsyncClient,
    leads_api_org: dict[str, object],
    db_ready: None,
) -> None:
    emails = leads_api_org["emails"]
    assert isinstance(emails, dict)
    lead_ids = leads_api_org["lead_ids"]
    assert isinstance(lead_ids, dict)
    token = await login(client, str(emails["op_a"]), str(leads_api_org["password"]))

    title_resp = await client.patch(
        f"/api/v1/leads/{lead_ids['open_a']}",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "x" * 501},
    )
    assert title_resp.status_code == 422

    fields_resp = await client.patch(
        f"/api/v1/leads/{lead_ids['open_a']}",
        headers={"Authorization": f"Bearer {token}"},
        json={"custom_fields": {f"k{i}": "v" for i in range(51)}},
    )
    assert fields_resp.status_code == 422

    depth_resp = await client.patch(
        f"/api/v1/leads/{lead_ids['open_a']}",
        headers={"Authorization": f"Bearer {token}"},
        json={"custom_fields": {"a": {"b": {"c": "too deep"}}}},
    )
    assert depth_resp.status_code == 422
