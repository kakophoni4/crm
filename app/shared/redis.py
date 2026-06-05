from __future__ import annotations

from redis.asyncio import Redis

from app.shared.settings import get_settings

_client: Redis | None = None


def get_redis() -> Redis:
    global _client
    if _client is None:
        _client = Redis.from_url(get_settings().redis_url, decode_responses=False)
    return _client


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
    _client = None


async def redis_ping() -> bool:
    try:
        ping_result = get_redis().ping()
        if isinstance(ping_result, bool):
            return ping_result
        return bool(await ping_result)
    except Exception:
        return False
