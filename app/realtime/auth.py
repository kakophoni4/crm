from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from redis.asyncio import Redis

from app.modules.db.models.user import User
from app.realtime.schemas import WsTicketResponse
from app.shared.exceptions import AuthenticationRequired
from app.shared.redis import get_redis
from app.shared.request_id import generate_ulid
from app.shared.security.deps import current_user
from app.shared.security.jwt import decode_ws_ticket, encode_ws_ticket
from app.shared.settings import get_settings

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

_WS_TICKET_KEY_PREFIX = "ws:ticket:"


def _ticket_redis_key(jti: str) -> str:
    return f"{_WS_TICKET_KEY_PREFIX}{jti}"


async def store_ws_ticket(
    redis: Redis,
    *,
    jti: str,
    user_id: int,
    role: str,
    department_id: int | None,
    group_id: int | None,
) -> None:
    settings = get_settings()
    payload = json.dumps(
        {
            "user_id": user_id,
            "role": role,
            "department_id": department_id,
            "group_id": group_id,
        },
    )
    await redis.setex(
        _ticket_redis_key(jti),
        settings.ws_ticket_ttl_seconds,
        payload,
    )


async def consume_ws_ticket(redis: Redis, ticket: str) -> dict[str, Any]:
    try:
        claims = decode_ws_ticket(ticket)
    except Exception as exc:
        raise AuthenticationRequired(message="Invalid or expired WebSocket ticket") from exc

    jti = str(claims["jti"])
    stored_raw = await redis.getdel(_ticket_redis_key(jti))
    if stored_raw is None:
        raise AuthenticationRequired(message="WebSocket ticket already used or expired")

    stored = json.loads(stored_raw)
    if int(stored["user_id"]) != int(claims["sub"]):
        raise AuthenticationRequired(message="Invalid WebSocket ticket")

    dept = stored.get("department_id")
    group = stored.get("group_id")
    return {
        "user_id": int(stored["user_id"]),
        "role": str(stored["role"]),
        "department_id": int(dept) if dept is not None else None,
        "group_id": int(group) if group is not None else None,
    }


@router.post("/ws-ticket", response_model=WsTicketResponse)
async def issue_ws_ticket(
    user: Annotated[User, Depends(current_user)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> WsTicketResponse:
    settings = get_settings()
    role = user.role.value if hasattr(user.role, "value") else str(user.role)
    jti = generate_ulid()
    ticket = encode_ws_ticket(user.id, role, jti)
    await store_ws_ticket(
        redis,
        jti=jti,
        user_id=user.id,
        role=role,
        department_id=user.department_id,
        group_id=user.group_id,
    )
    return WsTicketResponse(ticket=ticket, expires_in=settings.ws_ticket_ttl_seconds)
