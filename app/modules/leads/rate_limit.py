from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import MutableMapping

import structlog

from app.shared.exceptions import RateLimited
from app.shared.redis import get_redis
from app.shared.settings import get_settings

logger = structlog.get_logger(__name__)

_MEMORY_BUCKETS: MutableMapping[str, list[float]] = defaultdict(list)


def _check_in_memory(bucket_key: str, limit: int, *, message: str) -> None:
    now = time.monotonic()
    window = [stamp for stamp in _MEMORY_BUCKETS[bucket_key] if now - stamp < 60.0]
    if len(window) >= limit:
        raise RateLimited(
            message=message,
            details={"limit_per_minute": limit},
        )
    window.append(now)
    _MEMORY_BUCKETS[bucket_key] = window


async def _check_redis(bucket_key: str, limit: int, *, message: str) -> None:
    redis = get_redis()
    key = f"leads:rate:{bucket_key}".encode()
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, 60)
    if int(count) > limit:
        raise RateLimited(
            message=message,
            details={"limit_per_minute": limit},
        )


async def _enforce(user_id: int, *, scope: str, limit: int, message: str) -> None:
    if limit <= 0:
        return

    bucket_key = f"{scope}:{user_id}"
    settings = get_settings()
    if settings.leads_rate_limit_use_redis:
        try:
            await _check_redis(bucket_key, limit, message=message)
            return
        except RateLimited:
            raise
        except Exception:
            logger.warning("leads_rate_limit_redis_fallback", user_id=user_id, scope=scope)

    _check_in_memory(bucket_key, limit, message=message)


async def enforce_leads_list_rate_limit(user_id: int) -> None:
    settings = get_settings()
    await _enforce(
        user_id,
        scope="list",
        limit=settings.leads_list_rate_limit_per_minute,
        message="Leads list rate limit exceeded",
    )


async def enforce_leads_create_rate_limit(user_id: int) -> None:
    settings = get_settings()
    await _enforce(
        user_id,
        scope="create",
        limit=settings.leads_create_rate_limit_per_minute,
        message="Lead create rate limit exceeded",
    )


def reset_in_memory_rate_limits() -> None:
    """Test helper: clear in-memory counters."""
    _MEMORY_BUCKETS.clear()
