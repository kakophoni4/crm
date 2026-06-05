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
            "owner_type": "department",
            "owner_id": dept_id,
            "outbound_url": "https://bot.example.com/cmd2",
            "health_url": "https://bot.example.com/health2",
            "inbound_secret": "a" * 32,
            "outbound_secret": "b" * 32,
        },
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["secrets"]["inbound_secret"] == "a" * 32
    assert "inbound_secret" not in {k for k in data if k != "secrets"}

    listed = await client.get("/api/v1/bots", headers=admin_headers)
    assert listed.status_code == 200
    codes = {item["code"] for item in listed.json()["items"]}
    assert "admin_created_bot" in codes
