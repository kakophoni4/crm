from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.repository import AuthRepository
from app.modules.db.models.enums import UserStatus
from app.modules.db.models.user import User
from app.shared.db import get_db
from app.shared.exceptions import AppError, AuthenticationRequired
from app.shared.security.jwt import decode_token

_bearer_scheme = HTTPBearer(auto_error=False)


def bearer_token(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(_bearer_scheme),
    ],
) -> str:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthenticationRequired(message="Bearer token required")
    return credentials.credentials


async def current_user(
    token: Annotated[str, Depends(bearer_token)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    payload = decode_token(token)
    if payload.get("typ") != "access":
        raise AuthenticationRequired(
            message="Invalid access token",
            details={"code": "token_invalid"},
        )

    try:
        user_id = int(str(payload["sub"]))
    except (TypeError, ValueError) as exc:
        raise AuthenticationRequired(
            message="Invalid access token",
            details={"code": "token_invalid"},
        ) from exc

    repo = AuthRepository(db)
    user = await repo.get_user_by_id(user_id)
    if user is None or user.status != UserStatus.ACTIVE:
        raise AuthenticationRequired(message="Authentication required")

    return user


async def current_user_optional(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User | None:
    authorization = request.headers.get("Authorization")
    if not authorization:
        return None

    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None

    try:
        payload = decode_token(parts[1])
    except AppError:
        return None

    if payload.get("typ") != "access":
        return None

    try:
        user_id = int(str(payload["sub"]))
    except (TypeError, ValueError):
        return None

    repo = AuthRepository(db)
    user = await repo.get_user_by_id(user_id)
    if user is None or user.status != UserStatus.ACTIVE:
        return None

    return user
