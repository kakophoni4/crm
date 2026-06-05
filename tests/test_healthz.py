from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_healthz_ok(client: AsyncClient) -> None:
    response = await client.get("/healthz")
    assert response.status_code == 200
    payload = response.json()
    if not (payload["checks"]["db"] and payload["checks"]["redis"]):
        pytest.skip("PostgreSQL/Redis not available on configured URLs")
    assert payload["status"] == "ok"
    assert payload["checks"]["db"] is True
    assert payload["checks"]["redis"] is True
    assert payload["checks"]["worker"] is None
