from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_senior_assigns_bot_to_groups(
    client: AsyncClient,
    db_ready: None,
    senior_headers: dict[str, str],
    bots_org: dict[str, object],
    admin_headers: dict[str, str],
) -> None:
    dept_id = bots_org["dept_id"]
    group_id = bots_org["group_id"]
    create = await client.post(
        "/api/v1/bots",
        headers=admin_headers,
        json={
            "code": "dept_pool_bot",
            "name": "Dept Pool Bot",
            "department_id": dept_id,
            "outbound_url": "https://example.com/cmd",
            "inbound_secret": "a" * 32,
            "outbound_secret": "b" * 32,
        },
    )
    assert create.status_code == 201, create.text
    bot_id = create.json()["id"]

    response = await client.put(
        f"/api/v1/bots/{bot_id}/group-assignments",
        headers=senior_headers,
        json={"group_ids": [group_id]},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["assigned_group_ids"] == [group_id]
    assert group_id in data["assigned_group_ids"]
    assert "→" in data["owner_label"]

    clear = await client.put(
        f"/api/v1/bots/{bot_id}/group-assignments",
        headers=senior_headers,
        json={"group_ids": []},
    )
    assert clear.status_code == 200, clear.text
    assert clear.json()["assigned_group_ids"] == []
    assert "не распределён" in clear.json()["owner_label"]
