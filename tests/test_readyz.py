from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_readyz_ok_when_dependencies_up(client: AsyncClient) -> None:
    response = await client.get("/readyz")
    payload = response.json()
    if not (payload["checks"]["db"] and payload["checks"]["redis"]):
        pytest.skip("PostgreSQL/Redis not available on configured URLs")
    assert response.status_code == 200
    assert payload["status"] == "ready"
