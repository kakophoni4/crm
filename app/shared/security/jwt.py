from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from jose import JWTError, jwt  # type: ignore[import-untyped]

from app.shared.exceptions import AppError
from app.shared.settings import get_settings

TokenType = Literal["access", "refresh", "ws"]

_ALGORITHM = "HS256"


def _now() -> datetime:
    return datetime.now(UTC)


def _encode(
    *,
    sub: int,
    jti: str,
    typ: TokenType,
    ttl_seconds: int,
    role: str | None = None,
) -> str:
    settings = get_settings()
    issued_at = _now()
    payload: dict[str, Any] = {
        "sub": str(sub),
        "jti": jti,
        "iat": int(issued_at.timestamp()),
        "exp": int((issued_at + timedelta(seconds=ttl_seconds)).timestamp()),
        "typ": typ,
    }
    if role is not None:
        payload["role"] = role
    return str(jwt.encode(payload, settings.jwt_secret, algorithm=_ALGORITHM))


def encode_access(user_id: int, role: str, jti: str) -> str:
    settings = get_settings()
    return _encode(
        sub=user_id,
        role=role,
        jti=jti,
        typ="access",
        ttl_seconds=settings.jwt_access_ttl_seconds,
    )


def encode_refresh(user_id: int, jti: str) -> str:
    settings = get_settings()
    return _encode(
        sub=user_id,
        jti=jti,
        typ="refresh",
        ttl_seconds=settings.jwt_refresh_ttl_seconds,
    )


def decode_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[_ALGORITHM],
            options={"verify_exp": True},
        )
    except JWTError as exc:
        message = str(exc).lower()
        if "expired" in message:
            raise AppError(
                code="token_expired",
                message="Token has expired",
                status=401,
            ) from exc
        raise AppError(
            code="token_invalid",
            message="Invalid token",
            status=401,
        ) from exc

    for field in ("sub", "jti", "iat", "exp", "typ"):
        if field not in payload:
            raise AppError(
                code="token_invalid",
                message="Invalid token",
                status=401,
            )

    if payload["typ"] not in ("access", "refresh", "ws"):
        raise AppError(
            code="token_invalid",
            message="Invalid token",
            status=401,
        )

    return payload


def encode_ws_ticket(user_id: int, role: str, jti: str) -> str:
    settings = get_settings()
    return _encode(
        sub=user_id,
        role=role,
        jti=jti,
        typ="ws",
        ttl_seconds=settings.ws_ticket_ttl_seconds,
    )


def decode_ws_ticket(token: str) -> dict[str, Any]:
    payload = decode_token(token)
    if payload.get("typ") != "ws":
        raise AppError(
            code="token_invalid",
            message="Invalid WebSocket ticket",
            status=401,
        )
    return payload
