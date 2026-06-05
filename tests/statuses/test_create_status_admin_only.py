from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_status_forbidden_for_operator(
    client: AsyncClient,
    db_ready: None,
    operator_a_headers: dict[str, str],
) -> None:
    response = await client.post(
        "/api/v1/statuses",
        headers=operator_a_headers,
        json={
            "code": "custom_operator",
            "label": "Operator Status",
            "color": "#AABBCC",
            "sort_order": 99,
        },
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"


@pytest.mark.asyncio
async def test_create_status_allowed_for_senior(
    client: AsyncClient,
    db_ready: None,
    senior_headers: dict[str, str],
) -> None:
    response = await client.post(
        "/api/v1/statuses",
        headers=senior_headers,
        json={
            "code": "custom_senior",
            "label": "Senior Status",
            "color": "#AABBCC",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["code"] == "custom_senior"
    assert body["label"] == "Senior Status"


@pytest.mark.asyncio
async def test_create_status_as_admin(
    client: AsyncClient,
    db_ready: None,
    admin_headers: dict[str, str],
) -> None:
    response = await client.post(
        "/api/v1/statuses",
        headers=admin_headers,
        json={
            "code": "on_hold",
            "label": "На паузе",
            "color": "#9333EA",
            "sort_order": 50,
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["code"] == "on_hold"
    assert body["kind"] == "lead_pipeline"
    assert body["label"] == "На паузе"
    assert body["color"] == "#9333EA"
    assert body["sort_order"] == 50
    assert body["is_active"] is True
