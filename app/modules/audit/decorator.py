from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import wraps
from typing import Any, ParamSpec, TypeVar, get_args, get_origin, get_type_hints

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.service import AuditService
from app.modules.db.models.enums import AuditAction
from app.modules.db.models.user import User

P = ParamSpec("P")
T = TypeVar("T")


@dataclass(frozen=True)
class AuditedResult[T]:
    data: T
    entity_id: int
    payload: dict[str, Any]
    action: AuditAction | None = None
    skip: bool = False


def audit(
    action: AuditAction,
    entity_type: str,
) -> Callable[[Callable[P, Awaitable[AuditedResult[T]]]], Callable[P, Awaitable[T]]]:
    def decorator(
        func: Callable[P, Awaitable[AuditedResult[T]]],
    ) -> Callable[P, Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            result = await func(*args, **kwargs)
            actor = _extract_actor(kwargs)
            db = _extract_db(kwargs)
            request = _extract_request(kwargs)
            if db is not None:
                if not result.skip and actor is not None:
                    audit_service = AuditService(db)
                    effective_action = result.action if result.action is not None else action
                    await audit_service.write(
                        actor_id=actor.id,
                        action=effective_action,
                        entity_type=entity_type,
                        entity_id=result.entity_id,
                        payload=result.payload,
                        ip=_client_ip(request),
                        user_agent=_user_agent(request),
                    )
                await db.commit()
            return result.data

        return_hint = get_type_hints(func).get("return")
        if get_origin(return_hint) is AuditedResult:
            args = get_args(return_hint)
            if args:
                wrapper.__annotations__["return"] = args[0]
        return wrapper

    return decorator


def _extract_actor(kwargs: dict[str, Any]) -> User | None:
    for value in kwargs.values():
        if isinstance(value, User):
            return value
    return None


def _extract_db(kwargs: dict[str, Any]) -> AsyncSession | None:
    for value in kwargs.values():
        if isinstance(value, AsyncSession):
            return value
    return None


def _extract_request(kwargs: dict[str, Any]) -> Request | None:
    for value in kwargs.values():
        if isinstance(value, Request):
            return value
    return None


def _client_ip(request: Request | None) -> str | None:
    if request is None or request.client is None:
        return None
    return request.client.host


def _user_agent(request: Request | None) -> str | None:
    if request is None:
        return None
    return request.headers.get("user-agent")
