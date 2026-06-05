from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_me_without_token_returns_401(client: AsyncClient, db_ready: None) -> None:
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_required"


@pytest.mark.asyncio
async def test_me_with_valid_token(
    client: AsyncClient,
    auth_user: dict[str, object],
) -> None:
    access = str(auth_user["access_token"])
    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == auth_user["email"]
    assert body["role"] == "admin"
    assert isinstance(body["permissions"], list)
    assert "password_hash" not in body
