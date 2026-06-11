from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_admin_create_user_with_multiple_groups(
    client: AsyncClient,
    admin_headers: dict[str, str],
    db_ready: None,
) -> None:
    dept = await client.post(
        "/api/v1/departments",
        headers=admin_headers,
        json={"name": f"Multi Group Dept {uuid.uuid4().hex[:6]}"},
    )
    assert dept.status_code == 201, dept.text
    dept_id = dept.json()["id"]

    group_a = await client.post(
        "/api/v1/groups",
        headers=admin_headers,
        json={"name": f"Team A {uuid.uuid4().hex[:4]}", "department_id": dept_id},
    )
    group_b = await client.post(
        "/api/v1/groups",
        headers=admin_headers,
        json={"name": f"Team B {uuid.uuid4().hex[:4]}", "department_id": dept_id},
    )
    assert group_a.status_code == 201, group_a.text
    assert group_b.status_code == 201, group_b.text
    gid_a = group_a.json()["id"]
    gid_b = group_b.json()["id"]

    username = f"multi_{uuid.uuid4().hex[:8]}"
    response = await client.post(
        "/api/v1/users",
        headers=admin_headers,
        json={
            "username": username,
            "full_name": "Multi Group Operator",
            "password": "TempPass!234",
            "role": "user",
            "group_ids": [gid_a, gid_b],
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert set(body["group_ids"]) == {gid_a, gid_b}
    assert body["group_id"] is None

    me = await client.get(
        f"/api/v1/users/{body['id']}",
        headers=admin_headers,
    )
    assert me.status_code == 200, me.text
    assert set(me.json()["group_ids"]) == {gid_a, gid_b}


@pytest.mark.asyncio
async def test_reject_groups_from_different_departments(
    client: AsyncClient,
    admin_headers: dict[str, str],
    db_ready: None,
) -> None:
    dept_a = await client.post(
        "/api/v1/departments",
        headers=admin_headers,
        json={"name": f"Dept A {uuid.uuid4().hex[:6]}"},
    )
    dept_b = await client.post(
        "/api/v1/departments",
        headers=admin_headers,
        json={"name": f"Dept B {uuid.uuid4().hex[:6]}"},
    )
    assert dept_a.status_code == 201 and dept_b.status_code == 201
    ga = await client.post(
        "/api/v1/groups",
        headers=admin_headers,
        json={"name": "GA", "department_id": dept_a.json()["id"]},
    )
    gb = await client.post(
        "/api/v1/groups",
        headers=admin_headers,
        json={"name": "GB", "department_id": dept_b.json()["id"]},
    )
    response = await client.post(
        "/api/v1/users",
        headers=admin_headers,
        json={
            "username": f"bad_{uuid.uuid4().hex[:8]}",
            "full_name": "Bad Mix",
            "password": "TempPass!234",
            "role": "user",
            "group_ids": [ga.json()["id"], gb.json()["id"]],
        },
    )
    assert response.status_code == 422, response.text
