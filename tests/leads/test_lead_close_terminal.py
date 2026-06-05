from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.chats.conftest import login


@pytest.mark.asyncio
async def test_close_lead_requires_terminal_status(
    client: AsyncClient,
    leads_api_org: dict[str, object],
    db_ready: None,
) -> None:
    del db_ready
    emails = leads_api_org["emails"]
    assert isinstance(emails, dict)
    lead_ids = leads_api_org["lead_ids"]
    assert isinstance(lead_ids, dict)
    token = await login(client, str(emails["op_a"]), str(leads_api_org["password"]))

    bad_close = await client.post(
        f"/api/v1/leads/{lead_ids['open_a']}/close",
        headers={"Authorization": f"Bearer {token}"},
        json={"status_id": leads_api_org["pipeline_new"]},
    )
    assert bad_close.status_code == 422, bad_close.text

    ok_close = await client.post(
        f"/api/v1/leads/{lead_ids['open_a']}/close",
        headers={"Authorization": f"Bearer {token}"},
        json={"status_id": leads_api_org["pipeline_won"]},
    )
    assert ok_close.status_code == 200, ok_close.text
    assert ok_close.json()["status_id"] == leads_api_org["pipeline_won"]
    assert ok_close.json()["closed_at"] is not None


@pytest.mark.asyncio
async def test_patch_lead_cannot_set_terminal_status(
    client: AsyncClient,
    leads_api_org: dict[str, object],
    db_ready: None,
) -> None:
    del db_ready
    emails = leads_api_org["emails"]
    assert isinstance(emails, dict)
    lead_ids = leads_api_org["lead_ids"]
    assert isinstance(lead_ids, dict)
    token = await login(client, str(emails["op_a"]), str(leads_api_org["password"]))

    response = await client.patch(
        f"/api/v1/leads/{lead_ids['open_a']}",
        headers={"Authorization": f"Bearer {token}"},
        json={"status_id": leads_api_org["pipeline_lost"]},
    )
    assert response.status_code == 422, response.text
