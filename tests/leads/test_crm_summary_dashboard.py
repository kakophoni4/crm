from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine, text

from app.shared.settings import Settings
from tests.auth.conftest import _sync_database_url
from tests.chats.conftest import login


@pytest.mark.asyncio
async def test_user_crm_summary_scoped_to_own_group(
    client: AsyncClient,
    leads_api_org: dict[str, object],
    db_ready: None,
) -> None:
    del db_ready
    emails = leads_api_org["emails"]
    assert isinstance(emails, dict)
    token = await login(client, str(emails["op_a"]), str(leads_api_org["password"]))

    response = await client.get(
        "/api/v1/crm-summary",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["open_leads_count"] == 1
    assert body["closed_today_count"] == 0
    assert body["closed_leads_today_count"] == 0
    assert body["closed_won_today_count"] == 0
    assert body["closed_lost_today_count"] == 0
    assert body["by_operator"] == []
    assert "chats_today_count" in body
    assert "new_clients_today_count" in body
    assert "avg_response_minutes" in body
    assert body["by_pipeline_status"] == [
        {
            "status_id": leads_api_org["pipeline_new"],
            "code": "new",
            "label": body["by_pipeline_status"][0]["label"],
            "count": 1,
        },
    ]
    assert "contact_id" not in body
    assert "title" not in body
    assert "items" not in body


@pytest.mark.asyncio
async def test_user_b_sees_only_group_b_closed_not_open_a(
    client: AsyncClient,
    leads_api_org: dict[str, object],
    db_ready: None,
) -> None:
    del db_ready
    emails = leads_api_org["emails"]
    assert isinstance(emails, dict)
    token = await login(client, str(emails["op_b"]), str(leads_api_org["password"]))

    response = await client.get(
        "/api/v1/crm-summary",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["open_leads_count"] == 0
    assert body["closed_today_count"] == 0
    assert body["by_pipeline_status"] == []


@pytest.mark.asyncio
async def test_senior_sees_department_open_leads(
    client: AsyncClient,
    leads_api_org: dict[str, object],
    db_ready: None,
) -> None:
    del db_ready
    emails = leads_api_org["emails"]
    assert isinstance(emails, dict)
    token = await login(client, str(emails["senior"]), str(leads_api_org["password"]))

    response = await client.get(
        "/api/v1/crm-summary",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["open_leads_count"] == 1


@pytest.mark.asyncio
async def test_admin_sees_department_open_leads(
    client: AsyncClient,
    leads_api_org: dict[str, object],
    test_settings: Settings,
    db_ready: None,
) -> None:
    del db_ready, leads_api_org
    settings = test_settings
    engine = create_engine(_sync_database_url(settings.database_url))
    with engine.begin() as conn:
        admin_email = conn.execute(
            text("SELECT email FROM users WHERE role = 'admin' LIMIT 1"),
        ).scalar_one()
    engine.dispose()

    token = await login(client, str(admin_email), settings.seed_admin_password)
    response = await client.get(
        "/api/v1/crm-summary",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["open_leads_count"] >= 1


@pytest.mark.asyncio
async def test_closed_today_count_in_scope(
    client: AsyncClient,
    leads_api_org: dict[str, object],
    test_settings: Settings,
    db_ready: None,
) -> None:
    del db_ready
    emails = leads_api_org["emails"]
    assert isinstance(emails, dict)
    lead_ids = leads_api_org["lead_ids"]
    assert isinstance(lead_ids, dict)

    engine = create_engine(_sync_database_url(test_settings.database_url))
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE leads SET closed_at = now() WHERE id = :id"),
            {"id": lead_ids["closed_b"]},
        )
    engine.dispose()

    token = await login(client, str(emails["op_b"]), str(leads_api_org["password"]))
    response = await client.get(
        "/api/v1/crm-summary",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["closed_today_count"] == 1
    assert body["closed_won_today_count"] == 0
