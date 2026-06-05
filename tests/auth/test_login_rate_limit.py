from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.modules.auth.rate_limit import (
    reset_in_memory_login_rate_limits,
    reset_redis_login_rate_limits,
)
from app.shared.settings import get_settings


@pytest.mark.asyncio
async def test_login_rate_limit_returns_429(
    client: AsyncClient,
    db_ready: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOGIN_RATE_LIMIT_USE_REDIS", "false")
    monkeypatch.setenv("LOGIN_RATE_LIMIT_PER_MINUTE", "2")
    get_settings.cache_clear()
    reset_in_memory_login_rate_limits()

    for _ in range(2):
        response = await client.post(
            "/api/v1/auth/login",
            json={"username": "nobody", "password": "wrong-password-xyz"},
        )
        assert response.status_code == 401

    blocked = await client.post(
        "/api/v1/auth/login",
        json={"username": "nobody", "password": "wrong-password-xyz"},
    )
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "rate_limited"

    await reset_redis_login_rate_limits()
    reset_in_memory_login_rate_limits()
    get_settings.cache_clear()
