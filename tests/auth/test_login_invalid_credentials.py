from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_login_unknown_email_same_error(
    client: AsyncClient,
    db_ready: None,
    admin_credentials: dict[str, str],
) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "nobody", "password": admin_credentials["password"]},
    )
    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "invalid_credentials"


@pytest.mark.asyncio
async def test_login_wrong_password_same_error(
    client: AsyncClient,
    db_ready: None,
    admin_credentials: dict[str, str],
) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": admin_credentials["username"], "password": "wrong-password-xyz"},
    )
    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "invalid_credentials"


@pytest.mark.asyncio
async def test_login_invalid_credentials_same_message(
    client: AsyncClient,
    db_ready: None,
    admin_credentials: dict[str, str],
) -> None:
    unknown = await client.post(
        "/api/v1/auth/login",
        json={"username": "ghost", "password": "x"},
    )
    wrong = await client.post(
        "/api/v1/auth/login",
        json={"username": admin_credentials["username"], "password": "x"},
    )
    assert unknown.json()["error"]["message"] == wrong.json()["error"]["message"]
