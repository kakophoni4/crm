from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import MutableMapping

import structlog

from app.shared.exceptions import RateLimited
from app.shared.redis import get_redis
from app.shared.settings import get_settings

logger = structlog.get_logger(__name__)

_MEMORY_BUCKETS: MutableMapping[int, list[float]] = defaultdict(list)


def _check_in_memory(user_id: int, limit: int) -> None:
    now = time.monotonic()
    window = [stamp for stamp in _MEMORY_BUCKETS[user_id] if now - stamp < 60.0]
    if len(window) >= limit:
        raise RateLimited(
            message="Search rate limit exceeded",
            details={"limit_per_minute": limit},
        )
    window.append(now)
    _MEMORY_BUCKETS[user_id] = window


async def _check_redis(user_id: int, limit: int) -> None:
    redis = get_redis()
    key = f"search:rate:{user_id}".encode()
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, 60)
    if int(count) > limit:
        raise RateLimited(
            message="Search rate limit exceeded",
            details={"limit_per_minute": limit},
        )


async def enforce_search_rate_limit(user_id: int) -> None:
    settings = get_settings()
    limit = settings.search_rate_limit_per_minute
    if limit <= 0:
        return

    if settings.search_rate_limit_use_redis:
        try:
            await _check_redis(user_id, limit)
            return
        except RateLimited:
            raise
        except Exception:
            logger.warning("search_rate_limit_redis_fallback", user_id=user_id)

    _check_in_memory(user_id, limit)


def reset_in_memory_rate_limits() -> None:
    """Test helper: clear in-memory counters."""
    _MEMORY_BUCKETS.clear()
