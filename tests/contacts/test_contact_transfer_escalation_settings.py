from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_escalation_settings_get_and_patch(
    client: AsyncClient,
    db_ready: None,
    ownership_org: dict[str, object],
    ownership_senior_headers: dict[str, str],
) -> None:
    group_id = int(ownership_org["group_id"])

    get_resp = await client.get(
        f"/api/v1/groups/{group_id}/escalation-settings",
        headers=ownership_senior_headers,
    )
    assert get_resp.status_code == 200, get_resp.text
    assert get_resp.json()["first_response_timeout_minutes"] == 1

    patch_resp = await client.patch(
        f"/api/v1/groups/{group_id}/escalation-settings",
        headers=ownership_senior_headers,
        json={"first_response_timeout_minutes": 20},
    )
    assert patch_resp.status_code == 200, patch_resp.text
    assert patch_resp.json()["first_response_timeout_minutes"] == 20
