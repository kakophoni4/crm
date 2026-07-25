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
# Envelope-level delivery attempts (separate from handler payload retries).
_MAX_DELIVERY_ATTEMPTS = 5
_FAIL_BACKOFF_SECONDS = (5, 15, 60, 180, 600)

JobHandler = Callable[[str, dict[str, Any]], Awaitable[None]]

_handlers: dict[str, JobHandler] = {}
_worker_task: asyncio.Task[None] | None = None
_inflight_tasks: set[asyncio.Task[None]] = set()
_concurrency_sem: asyncio.Semaphore | None = None
_partition_locks: dict[str, asyncio.Lock] = {}
_partition_locks_guard = asyncio.Lock()


def register_handler(job_type: str, handler: JobHandler) -> None:
    _handlers[job_type] = handler


def _partition_key(job_type: str, payload: dict[str, Any]) -> str:
    """Jobs with the same key run sequentially; different keys may run in parallel."""
    if chat_id := payload.get("chat_id"):
        return f"chat:{chat_id}"
    # Prefer per-job keys before bot_id so a busy bot does not serialize all outbound.
    if log_id := payload.get("outbound_log_id"):
        return f"out:{log_id}"
    if message_id := payload.get("message_id"):
        return f"msg:{message_id}"
    if bot_id := payload.get("bot_id"):
        return f"bot:{bot_id}"
    if event_id := payload.get("event_id"):
        return f"evt:{event_id}"
    return f"type:{job_type}"


def _concurrency_limit() -> int:
    return max(1, get_settings().bot_job_concurrency)


def _get_sem() -> asyncio.Semaphore:
    global _concurrency_sem
    if _concurrency_sem is None:
        _concurrency_sem = asyncio.Semaphore(_concurrency_limit())
    return _concurrency_sem


async def _get_partition_lock(key: str) -> asyncio.Lock:
    async with _partition_locks_guard:
        lock = _partition_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            _partition_locks[key] = lock
        return lock


async def enqueue(
    job_type: str,
    payload: dict[str, Any],
    *,
    delay_seconds: int = 0,
    attempt: int = 0,
) -> None:
    redis = get_redis()
    body_obj: dict[str, Any] = {"type": job_type, "payload": payload}
    if attempt > 0:
        body_obj["attempt"] = attempt
    body = json.dumps(body_obj).encode("utf-8")
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


def _xautoclaim_entries(result: Any) -> list[tuple[Any, dict[bytes, bytes]]]:
    """Normalize redis-py XAUTOCLAIM reply: (next_id, messages[, deleted])."""
    if not result or not isinstance(result, (list, tuple)) or len(result) < 2:
        return []
    messages = result[1]
    if not messages:
        return []
    return list(messages)


async def _reclaim_stale_pending() -> None:
    settings = get_settings()
    idle_ms = settings.bot_job_reclaim_idle_ms
    if idle_ms <= 0:
        return
    redis = get_redis()
    try:
        result = await redis.xautoclaim(
            STREAM_KEY,
            CONSUMER_GROUP,
            WORKER_NAME,
            min_idle_time=idle_ms,
            start_id="0-0",
            count=10,
        )
    except Exception:
        logger.debug("bot_jobs_xautoclaim_skipped")
        return
    for message_id, fields in _xautoclaim_entries(result):
        mid = message_id if isinstance(message_id, bytes) else str(message_id).encode()
        task = asyncio.create_task(
            _handle_message(mid, fields),
            name=f"bot-job-{mid.decode()}",
        )
        _track_task(task)


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


async def _handle_message(message_id: bytes, fields: dict[bytes, bytes]) -> None:
    redis = get_redis()
    data = fields.get(b"data", b"{}")
    parsed = json.loads(data.decode("utf-8"))
    job_type = str(parsed.get("type", ""))
    payload = parsed.get("payload") or {}
    attempt = int(parsed.get("attempt") or 0)
    partition = _partition_key(job_type, payload)
    acked = False
    try:
        partition_lock = await _get_partition_lock(partition)
        async with partition_lock:
            async with _get_sem():
                await _process_message(fields)
        await redis.xack(STREAM_KEY, CONSUMER_GROUP, message_id)
        acked = True
        # Drop idle partition locks so the map does not grow without bound.
        if not partition_lock.locked():
            async with _partition_locks_guard:
                current = _partition_locks.get(partition)
                if current is partition_lock and not current.locked():
                    _partition_locks.pop(partition, None)
    except Exception:
        next_attempt = attempt + 1
        logger.exception(
            "bot_job_failed",
            message_id=message_id.decode(),
            job_type=job_type,
            attempt=next_attempt,
        )
        if acked:
            return
        # Ack + delayed requeue (or drop) so poison jobs do not hot-loop via xautoclaim.
        try:
            if next_attempt < _MAX_DELIVERY_ATTEMPTS:
                delay = _FAIL_BACKOFF_SECONDS[
                    min(next_attempt - 1, len(_FAIL_BACKOFF_SECONDS) - 1)
                ]
                await enqueue(
                    job_type,
                    payload if isinstance(payload, dict) else {},
                    delay_seconds=delay,
                    attempt=next_attempt,
                )
                logger.warning(
                    "bot_job_requeued",
                    job_type=job_type,
                    attempt=next_attempt,
                    delay_seconds=delay,
                )
            else:
                logger.error(
                    "bot_job_poison_skipped",
                    job_type=job_type,
                    attempt=next_attempt,
                    message_id=message_id.decode(),
                )
            await redis.xack(STREAM_KEY, CONSUMER_GROUP, message_id)
        except Exception:
            logger.exception(
                "bot_job_fail_recovery_error",
                message_id=message_id.decode(),
            )


def _track_task(task: asyncio.Task[None]) -> None:
    _inflight_tasks.add(task)
    task.add_done_callback(_inflight_tasks.discard)


async def _worker_loop() -> None:
    await _ensure_group()
    redis = get_redis()
    while True:
        try:
            await _promote_delayed()
            await _reclaim_stale_pending()
            limit = _concurrency_limit()
            available = limit - len(_inflight_tasks)
            if available <= 0:
                if _inflight_tasks:
                    await asyncio.wait(
                        _inflight_tasks,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                continue
            messages = await redis.xreadgroup(
                CONSUMER_GROUP,
                WORKER_NAME,
                {STREAM_KEY: ">"},
                count=min(10, available),
                block=2000,
            )
            if not messages:
                continue
            for _stream, entries in messages:
                for message_id, fields in entries:
                    task = asyncio.create_task(
                        _handle_message(message_id, fields),
                        name=f"bot-job-{message_id.decode()}",
                    )
                    _track_task(task)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("bot_worker_loop_error")
            await asyncio.sleep(1)


def start_worker() -> None:
    global _worker_task, _concurrency_sem
    if _worker_task is not None and not _worker_task.done():
        return
    _concurrency_sem = asyncio.Semaphore(_concurrency_limit())
    _worker_task = asyncio.create_task(_worker_loop(), name="bots-worker")


async def stop_worker() -> None:
    global _worker_task, _concurrency_sem
    if _worker_task is None:
        return
    _worker_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await _worker_task
    _worker_task = None
    if _inflight_tasks:
        await asyncio.gather(*list(_inflight_tasks), return_exceptions=True)
    _concurrency_sem = None
