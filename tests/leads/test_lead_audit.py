from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine, text

from app.shared.settings import Settings
from tests.auth.conftest import _sync_database_url
from tests.chats.conftest import login


def _count_lead_audit(
    engine_url: str,
    *,
    lead_id: int,
    action: str | None = None,
) -> int:
    engine = create_engine(engine_url)
    try:
        with engine.begin() as conn:
            if action is None:
                row = conn.execute(
                    text(
                        """
                        SELECT COUNT(*) FROM audit_log
                        WHERE entity_type = 'lead' AND entity_id = :lead_id
                        """
                    ),
                    {"lead_id": lead_id},
                ).scalar_one()
            else:
                row = conn.execute(
                    text(
                        """
                        SELECT COUNT(*) FROM audit_log
                        WHERE entity_type = 'lead' AND entity_id = :lead_id
                          AND action = :action
                        """
                    ),
                    {"lead_id": lead_id, "action": action},
                ).scalar_one()
            return int(row)
    finally:
        engine.dispose()


def _latest_lead_audit_action(engine_url: str, *, lead_id: int) -> str | None:
    engine = create_engine(engine_url)
    try:
        with engine.begin() as conn:
            return conn.execute(
                text(
                    """
                    SELECT action::text FROM audit_log
                    WHERE entity_type = 'lead' AND entity_id = :lead_id
                    ORDER BY id DESC
                    LIMIT 1
                    """
                ),
                {"lead_id": lead_id},
            ).scalar_one_or_none()
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_close_lead_writes_single_lead_close_audit(
    client: AsyncClient,
    leads_api_org: dict[str, object],
    test_settings: Settings,
    db_ready: None,
) -> None:
    emails = leads_api_org["emails"]
    assert isinstance(emails, dict)
    lead_ids = leads_api_org["lead_ids"]
    assert isinstance(lead_ids, dict)
    lead_id = int(lead_ids["open_a"])
    token = await login(client, str(emails["op_a"]), str(leads_api_org["password"]))
    db_url = _sync_database_url(test_settings.database_url)

    before = _count_lead_audit(db_url, lead_id=lead_id, action="lead.close")
    response = await client.post(
        f"/api/v1/leads/{lead_id}/close",
        headers={"Authorization": f"Bearer {token}"},
        json={"status_id": leads_api_org["pipeline_won"]},
    )
    assert response.status_code == 200, response.text
    after = _count_lead_audit(db_url, lead_id=lead_id, action="lead.close")
    assert after - before == 1
    assert _count_lead_audit(db_url, lead_id=lead_id) == after


@pytest.mark.asyncio
async def test_manual_create_lead_writes_single_lead_create_audit(
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
    db_url = _sync_database_url(test_settings.database_url)

    open_lead_id = int(lead_ids["open_a"])
    close_resp = await client.post(
        f"/api/v1/leads/{open_lead_id}/close",
        headers={"Authorization": f"Bearer {token}"},
        json={"status_id": leads_api_org["pipeline_won"]},
    )
    assert close_resp.status_code == 200, close_resp.text

    response = await client.post(
        f"/api/v1/contacts/{contact_id}/leads",
        headers={"Authorization": f"Bearer {token}"},
        json={"group_id": leads_api_org["group_a"]},
    )
    assert response.status_code == 201, response.text
    lead_id = response.json()["id"]
    assert _count_lead_audit(db_url, lead_id=lead_id, action="lead.create") == 1
    assert _count_lead_audit(db_url, lead_id=lead_id) == 1


@pytest.mark.asyncio
async def test_patch_fields_only_uses_lead_update_not_status_update(
    client: AsyncClient,
    leads_api_org: dict[str, object],
    test_settings: Settings,
    db_ready: None,
) -> None:
    emails = leads_api_org["emails"]
    assert isinstance(emails, dict)
    token = await login(client, str(emails["op_a"]), str(leads_api_org["password"]))
    contact_id = leads_api_org["contact_id"]
    db_url = _sync_database_url(test_settings.database_url)

    engine = create_engine(db_url)
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
                    INSERT INTO leads (
                        contact_id, group_id, chat_id, status_id
                    )
                    SELECT :cid, :gid, c.id, :status_id
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
        f"/api/v1/leads/{int(lead_id)}",
        headers={"Authorization": f"Bearer {token}"},
        json={"custom_fields": {"order": {"service": "Audit service"}}},
    )
    assert response.status_code == 200, response.text
    assert response.json()["custom_fields"]["order"]["service"] == "Audit service"
    assert _latest_lead_audit_action(db_url, lead_id=int(lead_id)) == "lead.update"
    assert _count_lead_audit(db_url, lead_id=int(lead_id), action="lead.status.update") == 0
