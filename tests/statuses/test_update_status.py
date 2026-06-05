from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_update_status_as_admin(
    client: AsyncClient,
    db_ready: None,
    admin_headers: dict[str, str],
) -> None:
    listing = await client.get("/api/v1/statuses", headers=admin_headers)
    assert listing.status_code == 200
    target = next(item for item in listing.json()["items"] if item["code"] == "new")

    response = await client.patch(
        f"/api/v1/statuses/{target['id']}",
        headers=admin_headers,
        json={"label": "Новый лид", "color": "#111111", "sort_order": 1},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["label"] == "Новый лид"
    assert body["color"] == "#111111"
    assert body["sort_order"] == 1


@pytest.mark.asyncio
async def test_update_status_forbidden_for_operator(
    client: AsyncClient,
    db_ready: None,
    operator_a_headers: dict[str, str],
    admin_headers: dict[str, str],
) -> None:
    listing = await client.get("/api/v1/statuses", headers=admin_headers)
    target = listing.json()["items"][0]

    response = await client.patch(
        f"/api/v1/statuses/{target['id']}",
        headers=operator_a_headers,
        json={"label": "Hack"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_delete_status_soft_deactivates(
    client: AsyncClient,
    db_ready: None,
    admin_headers: dict[str, str],
) -> None:
    create = await client.post(
        "/api/v1/statuses",
        headers=admin_headers,
        json={
            "code": "temp_pipeline_stage",
            "kind": "lead_pipeline",
            "label": "Временный этап",
        },
    )
    assert create.status_code == 201
    status_id = create.json()["id"]

    delete = await client.delete(f"/api/v1/statuses/{status_id}", headers=admin_headers)
    assert delete.status_code == 200, delete.text

    listing = await client.get(
        "/api/v1/statuses",
        headers=admin_headers,
        params={"kind": "lead_pipeline", "include_inactive": True},
    )
    codes = {item["code"] for item in listing.json()["items"]}
    assert "temp_pipeline_stage" not in codes


@pytest.mark.asyncio
async def test_delete_system_pipeline_stage_rejected(
    client: AsyncClient,
    db_ready: None,
    admin_headers: dict[str, str],
) -> None:
    listing = await client.get(
        "/api/v1/statuses",
        headers=admin_headers,
        params={"kind": "lead_pipeline"},
    )
    assert listing.status_code == 200
    target = next(item for item in listing.json()["items"] if item["code"] == "new")

    response = await client.delete(f"/api/v1/statuses/{target['id']}", headers=admin_headers)
    assert response.status_code == 422, response.text
    assert "Системный этап" in response.json()["error"]["message"]


@pytest.mark.asyncio
async def test_delete_custom_pipeline_stage_without_leads(
    client: AsyncClient,
    db_ready: None,
    admin_headers: dict[str, str],
) -> None:
    create = await client.post(
        "/api/v1/statuses",
        headers=admin_headers,
        json={
            "code": "custom_stage_delete_me",
            "kind": "lead_pipeline",
            "label": "Удаляемый этап",
        },
    )
    assert create.status_code == 201
    status_id = create.json()["id"]

    response = await client.delete(f"/api/v1/statuses/{status_id}", headers=admin_headers)
    assert response.status_code == 200, response.text
