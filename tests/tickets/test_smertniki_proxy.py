from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_admin_can_create_lawyer(
    client: AsyncClient,
    admin_headers: dict[str, str],
    db_ready: None,
) -> None:
    username = f"lawyer_{uuid.uuid4().hex[:8]}"
    response = await client.post(
        "/api/v1/users",
        headers=admin_headers,
        json={
            "username": username,
            "full_name": "Юрист Тест",
            "password": "TempPass!234",
            "role": "lawyer",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["role"] == "lawyer"
    assert body["department_id"] is None
    assert body["group_id"] is None


@pytest.mark.asyncio
async def test_tickets_unconfigured_returns_503(
    client: AsyncClient,
    admin_headers: dict[str, str],
    db_ready: None,
) -> None:
    response = await client.get("/api/v1/tickets/companies", headers=admin_headers)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "smertniki_unavailable"
