from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_bots_requires_auth(client: AsyncClient, db_ready: None) -> None:
    response = await client.get("/api/v1/bots")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_operator_cannot_create_bot(
    client: AsyncClient,
    db_ready: None,
    operator_headers: dict[str, str],
    bots_org: dict[str, object],
) -> None:
    dept_id = bots_org["dept_id"]
    response = await client.post(
        "/api/v1/bots",
        headers=operator_headers,
        json={
            "code": "new_bot_x",
            "name": "New",
            "owner_type": "department",
            "owner_id": dept_id,
            "outbound_url": "https://example.com/cmd",
            "inbound_secret": "x" * 32,
            "outbound_secret": "y" * 32,
        },
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_creates_and_lists_bot(
    client: AsyncClient,
    db_ready: None,
    admin_headers: dict[str, str],
    bots_org: dict[str, object],
) -> None:
    dept_id = bots_org["dept_id"]
    response = await client.post(
        "/api/v1/bots",
        headers=admin_headers,
        json={
            "code": "admin_created_bot",
            "name": "Admin Bot",
            "department_id": dept_id,
            "outbound_url": "https://bot.example.com/cmd2",
            "health_url": "https://bot.example.com/health2",
            "inbound_secret": "a" * 32,
            "outbound_secret": "b" * 32,
        },
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["department_id"] == dept_id
    assert data["department_name"] is not None
    assert data["secrets"]["inbound_secret"] == "a" * 32
    assert "inbound_secret" not in {k for k in data if k != "secrets"}

    listed = await client.get("/api/v1/bots", headers=admin_headers)
    assert listed.status_code == 200
    codes = {item["code"] for item in listed.json()["items"]}
    assert "admin_created_bot" in codes


@pytest.mark.asyncio
async def test_update_bot_name_preserves_group_assignments(
    client: AsyncClient,
    db_ready: None,
    admin_headers: dict[str, str],
    senior_headers: dict[str, str],
    bots_org: dict[str, object],
) -> None:
    dept_id = bots_org["dept_id"]
    group_id = bots_org["group_id"]
    create = await client.post(
        "/api/v1/bots",
        headers=admin_headers,
        json={
            "code": "preserve_groups_bot",
            "name": "Before Rename",
            "department_id": dept_id,
            "outbound_url": "https://example.com/cmd",
            "inbound_secret": "a" * 32,
            "outbound_secret": "b" * 32,
        },
    )
    assert create.status_code == 201, create.text
    bot_id = create.json()["id"]

    assigned = await client.put(
        f"/api/v1/bots/{bot_id}/group-assignments",
        headers=senior_headers,
        json={"group_ids": [group_id]},
    )
    assert assigned.status_code == 200, assigned.text

    updated = await client.patch(
        f"/api/v1/bots/{bot_id}",
        headers=admin_headers,
        json={"name": "After Rename", "department_id": dept_id},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "After Rename"
    assert updated.json()["assigned_group_ids"] == [group_id]


@pytest.mark.asyncio
async def test_bot_service_types_default_and_update(
    client: AsyncClient,
    db_ready: None,
    admin_headers: dict[str, str],
    bots_org: dict[str, object],
) -> None:
    dept_id = bots_org["dept_id"]
    create = await client.post(
        "/api/v1/bots",
        headers=admin_headers,
        json={
            "code": "service_types_bot",
            "name": "Services Bot",
            "department_id": dept_id,
            "outbound_url": "https://example.com/cmd",
            "inbound_secret": "a" * 32,
            "outbound_secret": "b" * 32,
            "service_types": ["ОПТ"],
        },
    )
    assert create.status_code == 201, create.text
    bot_id = create.json()["id"]
    assert create.json()["service_types"] == ["ОПТ"]

    updated = await client.patch(
        f"/api/v1/bots/{bot_id}",
        headers=admin_headers,
        json={"service_types": ["Деревья", "ОПТ"]},
    )
    assert updated.status_code == 200, updated.text
    assert set(updated.json()["service_types"]) == {"Деревья", "ОПТ"}

    listed = await client.get("/api/v1/bots", headers=admin_headers)
    row = next(item for item in listed.json()["items"] if item["id"] == bot_id)
    assert set(row["service_types"]) == {"Деревья", "ОПТ"}
