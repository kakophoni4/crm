from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.shared.settings import Settings, get_settings
from tests.auth.conftest import _sync_database_url
from tests.chats.conftest import login


@pytest.mark.asyncio
async def test_contact_crm_summary_uses_redis_cache(
    client: AsyncClient,
    leads_api_org: dict[str, object],
    test_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    db_ready: None,
) -> None:
    del db_ready
    monkeypatch.setenv("CRM_SUMMARY_CACHE_ENABLED", "true")
    monkeypatch.setenv("CRM_SUMMARY_CACHE_TTL_SECONDS", "300")
    get_settings.cache_clear()

    contact_id = int(leads_api_org["contact_id"])
    token = await login(
        client,
        str(leads_api_org["emails"]["op_a"]),
        str(leads_api_org["password"]),
    )
    headers = {"Authorization": f"Bearer {token}"}

    first = await client.get(f"/api/v1/contacts/{contact_id}", headers=headers)
    assert first.status_code == 200, first.text
    summary1 = first.json()["crm_summary"]

    from sqlalchemy import create_engine, text

    engine = create_engine(_sync_database_url(test_settings.database_url))
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO leads (
                        contact_id, group_id, status_id, closed_at, title
                    )
                    VALUES (
                        :cid,
                        :gid,
                        (
                            SELECT id FROM statuses
                            WHERE code = 'new' AND kind = 'lead_pipeline'
                            LIMIT 1
                        ),
                        now(),
                        'Cache probe closed'
                    )
                    """
                ),
                {"cid": contact_id, "gid": leads_api_org["group_a"]},
            )
    finally:
        engine.dispose()

    second = await client.get(f"/api/v1/contacts/{contact_id}", headers=headers)
    assert second.status_code == 200
    summary2 = second.json()["crm_summary"]
    assert summary2 == summary1

    from app.modules.leads.crm_cache import contact_crm_cache_key, invalidate_contact_crm
    from app.shared.redis import get_redis

    await invalidate_contact_crm(get_redis(), contact_id)
    assert contact_crm_cache_key(contact_id).startswith("crm_summary:contact:")

    third = await client.get(f"/api/v1/contacts/{contact_id}", headers=headers)
    assert third.status_code == 200
    assert third.json()["crm_summary"]["prior_leads_count"] >= summary1["prior_leads_count"] + 1
