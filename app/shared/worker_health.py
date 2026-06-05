from __future__ import annotations

import asyncio
import contextlib
import time

import structlog

from app.shared.redis import get_redis

logger = structlog.get_logger(__name__)

WORKER_HEALTH_KEY = "crm:worker:health-check"
WORKER_HEALTH_TTL_SECONDS = 60
_HEARTBEAT_INTERVAL_SECONDS = 30

_heartbeat_task: asyncio.Task[None] | None = None


async def touch_worker_health() -> None:
    redis = get_redis()
    await redis.set(
        WORKER_HEALTH_KEY,
        str(time.time()).encode(),
        ex=WORKER_HEALTH_TTL_SECONDS,
    )


async def worker_ping() -> bool:
    """Return True if a CRM worker recently wrote a Redis heartbeat."""
    try:
        redis = get_redis()
        val = await redis.get(WORKER_HEALTH_KEY)
        return val is not None
    except Exception:
        return False


async def _heartbeat_loop() -> None:
    while True:
        try:
            await touch_worker_health()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.debug("worker_health_touch_failed")
        await asyncio.sleep(_HEARTBEAT_INTERVAL_SECONDS)


def start_worker_heartbeat() -> None:
    global _heartbeat_task
    if _heartbeat_task is not None and not _heartbeat_task.done():
        return
    _heartbeat_task = asyncio.create_task(_heartbeat_loop(), name="worker-health-heartbeat")


async def stop_worker_heartbeat() -> None:
    global _heartbeat_task
    if _heartbeat_task is None:
        return
    _heartbeat_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await _heartbeat_task
    _heartbeat_task = None
