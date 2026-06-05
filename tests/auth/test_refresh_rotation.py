from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_refresh_rotation_old_token_rejected(
    client: AsyncClient,
    auth_user: dict[str, object],
) -> None:
    old_refresh = str(auth_user["refresh_token"])
    rotated = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": old_refresh},
    )
    assert rotated.status_code == 200
    new_body = rotated.json()
    assert new_body["access_token"]
    assert new_body["refresh_token"] != old_refresh

    reuse = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": old_refresh},
    )
    assert reuse.status_code == 401
    assert reuse.json()["error"]["code"] == "token_invalid"
