from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from jose import jwt

from app.shared.exceptions import AppError
from app.shared.security import jwt as jwt_module
from app.shared.settings import get_settings


def _expired_access_token(user_id: int, role: str, jti: str) -> str:
    settings = get_settings()
    expired_at = datetime.now(UTC) - timedelta(hours=1)
    payload = {
        "sub": str(user_id),
        "role": role,
        "jti": jti,
        "iat": int((expired_at - timedelta(hours=1)).timestamp()),
        "exp": int(expired_at.timestamp()),
        "typ": "access",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


@pytest.mark.asyncio
async def test_access_token_expired_returns_401(
    client: AsyncClient,
    auth_user: dict[str, object],
) -> None:
    user = auth_user["user"]
    assert isinstance(user, dict)
    access = _expired_access_token(int(user["id"]), str(user["role"]), "expired-jti-test")

    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "token_expired"


def test_decode_expired_refresh_token() -> None:
    expired_at = datetime.now(UTC) - timedelta(hours=1)
    settings = get_settings()
    payload = {
        "sub": "1",
        "jti": "refresh-expired-jti",
        "iat": int((expired_at - timedelta(hours=1)).timestamp()),
        "exp": int(expired_at.timestamp()),
        "typ": "refresh",
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")

    with pytest.raises(AppError) as exc_info:
        jwt_module.decode_token(token)

    assert exc_info.value.code == "token_expired"
