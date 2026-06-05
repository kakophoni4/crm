from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_statuses_as_operator(
    client: AsyncClient,
    db_ready: None,
    operator_a_headers: dict[str, str],
) -> None:
    response = await client.get("/api/v1/statuses", headers=operator_a_headers)
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert len(items) >= 5
    assert all(item["is_active"] for item in items)


@pytest.mark.asyncio
async def test_list_statuses_as_senior(
    client: AsyncClient,
    db_ready: None,
    senior_headers: dict[str, str],
) -> None:
    response = await client.get("/api/v1/statuses", headers=senior_headers)
    assert response.status_code == 200, response.text
    assert len(response.json()["items"]) >= 5


@pytest.mark.asyncio
async def test_list_statuses_requires_auth(client: AsyncClient, db_ready: None) -> None:
    response = await client.get("/api/v1/statuses")
    assert response.status_code == 401
