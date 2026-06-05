from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_admin_post_users_returns_201(
    client: AsyncClient,
    admin_headers: dict[str, str],
    db_ready: None,
) -> None:
    dept = await client.post(
        "/api/v1/departments",
        headers=admin_headers,
        json={"name": f"RBAC Dept {uuid.uuid4().hex[:6]}"},
    )
    assert dept.status_code == 201, dept.text
    dept_id = dept.json()["id"]
    group = await client.post(
        "/api/v1/groups",
        headers=admin_headers,
        json={"name": "RBAC Group", "department_id": dept_id},
    )
    assert group.status_code == 201, group.text
    group_id = group.json()["id"]
    username = f"admin_created_{uuid.uuid4().hex[:8]}"
    response = await client.post(
        "/api/v1/users",
        headers=admin_headers,
        json={
            "username": username,
            "full_name": "Admin Created User",
            "password": "TempPass!234",
            "role": "user",
            "group_id": group_id,
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["username"] == username
    assert body["email"] == f"{username}@crm.local"
    assert body["group_id"] == group_id


@pytest.mark.asyncio
async def test_admin_post_senior_with_department_returns_201(
    client: AsyncClient,
    admin_headers: dict[str, str],
    db_ready: None,
) -> None:
    dept = await client.post(
        "/api/v1/departments",
        headers=admin_headers,
        json={"name": f"Senior Dept {uuid.uuid4().hex[:6]}"},
    )
    assert dept.status_code == 201, dept.text
    dept_id = dept.json()["id"]
    username = f"senior_{uuid.uuid4().hex[:8]}"
    response = await client.post(
        "/api/v1/users",
        headers=admin_headers,
        json={
            "username": username,
            "full_name": "Department Senior",
            "password": "TempPass!234",
            "role": "senior",
            "department_id": dept_id,
            "set_as_department_head": True,
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["role"] == "senior"
    assert body["department_id"] == dept_id
    assert body["group_id"] is None

    dept_list = await client.get("/api/v1/departments", headers=admin_headers)
    assert dept_list.status_code == 200, dept_list.text
    match = next(item for item in dept_list.json()["items"] if item["id"] == dept_id)
    assert match["head_user_id"] == body["id"]


@pytest.mark.asyncio
async def test_operator_post_users_returns_403(
    client: AsyncClient,
    operator_a_headers: dict[str, str],
    chats_org: dict[str, object],
    db_ready: None,
) -> None:
    me = await client.get("/api/v1/auth/me", headers=operator_a_headers)
    assert me.status_code == 200
    group_id = me.json()["group_id"]
    assert group_id is not None
    response = await client.post(
        "/api/v1/users",
        headers=operator_a_headers,
        json={
            "username": f"denied_{uuid.uuid4().hex[:8]}",
            "full_name": "Denied User",
            "password": "TempPass!234",
            "role": "user",
            "group_id": group_id,
        },
    )
    assert response.status_code == 403
