from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_logout_revokes_refresh(
    client: AsyncClient,
    auth_user: dict[str, object],
) -> None:
    access = str(auth_user["access_token"])
    refresh = str(auth_user["refresh_token"])

    logout = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": refresh},
        headers={"Authorization": f"Bearer {access}"},
    )
    assert logout.status_code == 200
    assert logout.json()["ok"] is True

    refresh_again = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh},
    )
    assert refresh_again.status_code == 401
    assert refresh_again.json()["error"]["code"] == "token_invalid"
