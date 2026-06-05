from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.chats.conftest import login


@pytest.mark.asyncio
async def test_group_b_sees_prior_count_but_not_group_a_leads(
    client: AsyncClient,
    leads_api_org: dict[str, object],
    db_ready: None,
) -> None:
    del db_ready
    emails = leads_api_org["emails"]
    assert isinstance(emails, dict)
    token = await login(client, str(emails["op_b"]), str(leads_api_org["password"]))
    contact_id = leads_api_org["contact_id"]
    headers = {"Authorization": f"Bearer {token}"}

    detail = await client.get(f"/api/v1/contacts/{contact_id}", headers=headers)
    assert detail.status_code == 200, detail.text
    summary = detail.json()["crm_summary"]
    assert summary["prior_leads_count"] == 2

    leads_resp = await client.get(
        f"/api/v1/contacts/{contact_id}/leads",
        headers=headers,
    )
    assert leads_resp.status_code == 200, leads_resp.text
    items = leads_resp.json()["items"]
    group_ids = {item["group_id"] for item in items}
    titles = {item.get("title") for item in items}

    assert group_ids == {leads_api_org["group_b"]}
    assert "Closed B" in titles
    assert "Closed A" not in titles
    assert "Open A" not in titles
