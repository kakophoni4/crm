from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_login_success(
    client: AsyncClient,
    db_ready: None,
    admin_credentials: dict[str, str],
) -> None:
    response = await client.post("/api/v1/auth/login", json=admin_credentials)
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "Bearer"
    assert body["expires_in"] == 900
    assert isinstance(body["access_token"], str) and body["access_token"]
    assert isinstance(body["refresh_token"], str) and body["refresh_token"]
    assert body["user"]["email"] == "admin@crm.local"
    assert body["user"]["role"] == "admin"
    assert "password" not in body
    assert "password_hash" not in body
