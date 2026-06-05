from __future__ import annotations

import asyncio
import contextlib
import json
import time
from collections.abc import Awaitable, Callable
from typing import Any

import structlog

from app.shared.redis import get_redis
from app.shared.redis_delayed import promote_delayed_jobs
from app.shared.settings import get_settings

logger = structlog.get_logger(__name__)

STREAM_KEY = "crm:bots:jobs"
DELAYED_KEY = "crm:bots:jobs:delayed"
CONSUMER_GROUP = "bots-workers"
WORKER_NAME = "worker-1"

JobHandler = Callable[[str, dict[str, Any]], Awaitable[None]]

_handlers: dict[str, JobHandler] = {}
_worker_task: asyncio.Task[None] | None = None


def register_handler(job_type: str, handler: JobHandler) -> None:
    _handlers[job_type] = handler


async def enqueue(
    job_type: str,
    payload: dict[str, Any],
    *,
    delay_seconds: int = 0,
) -> None:
    redis = get_redis()
    body = json.dumps({"type": job_type, "payload": payload}).encode("utf-8")
    if delay_seconds > 0:
        run_at = time.time() + delay_seconds
        await redis.zadd(DELAYED_KEY, {body: run_at})
        return
    await redis.xadd(STREAM_KEY, {"data": body})


async def _promote_delayed(limit: int = 50) -> None:
    redis = get_redis()
    await promote_delayed_jobs(
        redis,
        delayed_key=DELAYED_KEY,
        stream_key=STREAM_KEY,
        limit=limit,
    )


async def _reclaim_stale_pending() -> None:
    settings = get_settings()
    idle_ms = settings.bot_job_reclaim_idle_ms
    if idle_ms <= 0:
        return
    redis = get_redis()
    try:
        await redis.xautoclaim(
            STREAM_KEY,
            CONSUMER_GROUP,
            WORKER_NAME,
            min_idle_time=idle_ms,
            start_id="0-0",
            count=10,
        )
    except Exception:
        logger.debug("bot_jobs_xautoclaim_skipped")


async def _ensure_group() -> None:
    redis = get_redis()
    try:
        await redis.xgroup_create(STREAM_KEY, CONSUMER_GROUP, id="0", mkstream=True)
    except Exception as exc:
        if "BUSYGROUP" not in str(exc):
            logger.debug("redis_group_exists", error=str(exc))


async def _process_message(raw: dict[bytes, bytes]) -> None:
    data = raw.get(b"data", b"{}")
    parsed = json.loads(data.decode("utf-8"))
    job_type = str(parsed.get("type", ""))
    payload = parsed.get("payload") or {}
    handler = _handlers.get(job_type)
    if handler is None:
        logger.warning("unknown_bot_job", job_type=job_type)
        return
    await handler(job_type, payload)


async def _worker_loop() -> None:
    await _ensure_group()
    redis = get_redis()
    while True:
        try:
            await _promote_delayed()
            await _reclaim_stale_pending()
            messages = await redis.xreadgroup(
                CONSUMER_GROUP,
                WORKER_NAME,
                {STREAM_KEY: ">"},
                count=10,
                block=2000,
            )
            if not messages:
                continue
            for _stream, entries in messages:
                for message_id, fields in entries:
                    try:
                        await _process_message(fields)
                        await redis.xack(STREAM_KEY, CONSUMER_GROUP, message_id)
                    except Exception:
                        logger.exception("bot_job_failed", message_id=message_id.decode())
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("bot_worker_loop_error")
            await asyncio.sleep(1)


def start_worker() -> None:
    global _worker_task
    if _worker_task is not None and not _worker_task.done():
        return
    _worker_task = asyncio.create_task(_worker_loop(), name="bots-worker")


async def stop_worker() -> None:
    global _worker_task
    if _worker_task is None:
        return
    _worker_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await _worker_task
    _worker_task = None
