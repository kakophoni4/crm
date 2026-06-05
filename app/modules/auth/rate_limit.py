from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import Awaitable, Callable, MutableMapping
from functools import wraps
from typing import Any

import structlog
from fastapi import Request

from app.shared.exceptions import RateLimited
from app.shared.redis import get_redis
from app.shared.settings import get_settings

logger = structlog.get_logger(__name__)

_MEMORY_BUCKETS: MutableMapping[str, list[float]] = defaultdict(list)

def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _check_in_memory(ip: str, limit: int) -> None:
    now = time.monotonic()
    window = [stamp for stamp in _MEMORY_BUCKETS[ip] if now - stamp < 60.0]
    if len(window) >= limit:
        raise RateLimited(
            message="Too many login attempts",
            details={"limit_per_minute": limit},
        )
    window.append(now)
    _MEMORY_BUCKETS[ip] = window


async def _check_redis(ip: str, limit: int) -> None:
    redis = get_redis()
    key = f"auth:login:{ip}".encode()
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, 60)
    if int(count) > limit:
        raise RateLimited(
            message="Too many login attempts",
            details={"limit_per_minute": limit},
        )


async def enforce_login_rate_limit(request: Request) -> None:
    settings = get_settings()
    limit = settings.login_rate_limit_per_minute
    if limit <= 0:
        return

    ip = _client_ip(request)
    if settings.login_rate_limit_use_redis:
        try:
            await _check_redis(ip, limit)
            return
        except RateLimited:
            raise
        except Exception:
            logger.warning("login_rate_limit_redis_fallback", ip=ip)

    _check_in_memory(ip, limit)


def login_rate_limit[F: Callable[..., Awaitable[Any]]](func: F) -> F:
    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        request: Request | None = kwargs.get("request")
        if request is None:
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
        if request is not None:
            await enforce_login_rate_limit(request)
        return await func(*args, **kwargs)

    return wrapper  # type: ignore[return-value]


def reset_in_memory_login_rate_limits() -> None:
    _MEMORY_BUCKETS.clear()


async def reset_redis_login_rate_limits() -> None:
    try:
        redis = get_redis()
        keys = await redis.keys("auth:login:*")
        if keys:
            await redis.delete(*keys)
    except Exception:
        logger.debug("login_rate_limit_redis_reset_skipped")
