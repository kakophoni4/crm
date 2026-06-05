from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_custom_field_filter_via_gin(
    client: AsyncClient,
    admin_headers: dict[str, str],
) -> None:
    await client.post(
        "/api/v1/contacts",
        headers=admin_headers,
        json={"full_name": "Moscow Lead", "custom_fields": {"city": "Moscow"}},
    )
    await client.post(
        "/api/v1/contacts",
        headers=admin_headers,
        json={"full_name": "SPB Lead", "custom_fields": {"city": "SPB"}},
    )

    response = await client.get(
        "/api/v1/contacts",
        headers=admin_headers,
        params={"custom_field[city]": "Moscow"},
    )
    assert response.status_code == 200, response.text
    names = {item["full_name"] for item in response.json()["items"]}
    assert "Moscow Lead" in names
    assert "SPB Lead" not in names
