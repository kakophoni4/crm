from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import structlog
from pydantic import BaseModel, Field

from app.shared.redis import get_redis

logger = structlog.get_logger(__name__)

REDIS_EVENTS_CHANNEL = b"crm:events"

_subscriber_queues: set[asyncio.Queue[Event]] = set()
_local_lock = asyncio.Lock()


class Event(BaseModel):
    topic: str
    payload: dict[str, Any]
    scope: dict[str, Any] = Field(default_factory=dict)


def _encode_event(event: Event) -> bytes:
    return event.model_dump_json().encode("utf-8")


def _decode_event(raw: bytes) -> Event:
    return Event.model_validate_json(raw)


async def _notify_local(event: Event) -> None:
    async with _local_lock:
        queues = list(_subscriber_queues)
    for queue in queues:
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning("realtime_subscriber_queue_full", topic=event.topic)


async def publish(
    topic: str,
    payload: dict[str, Any],
    *,
    scope: dict[str, Any] | None = None,
) -> None:
    event = Event(topic=topic, payload=payload, scope=scope or {})
    await _notify_local(event)
    try:
        redis = get_redis()
        await redis.publish(REDIS_EVENTS_CHANNEL, _encode_event(event))
    except Exception:
        logger.exception("realtime_redis_publish_failed", topic=topic)


async def subscribe() -> AsyncIterator[Event]:
    """Yield domain events from the in-process bus (fed by publish and Redis bridge)."""
    queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=256)
    async with _local_lock:
        _subscriber_queues.add(queue)
    try:
        while True:
            yield await queue.get()
    finally:
        async with _local_lock:
            _subscriber_queues.discard(queue)


async def redis_events_listener(
    *,
    on_event: Any,
    stopped: asyncio.Event,
) -> None:
    """Read Redis Pub/Sub and fan-in to local subscribers (reconnects on failure)."""
    while not stopped.is_set():
        pubsub = None
        try:
            redis = get_redis()
            pubsub = redis.pubsub()
            await pubsub.subscribe(REDIS_EVENTS_CHANNEL)
            while not stopped.is_set():
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0,
                )
                if message is None:
                    continue
                if message.get("type") != "message":
                    continue
                data = message.get("data")
                if not isinstance(data, (bytes, bytearray)):
                    continue
                event = _decode_event(bytes(data))
                await on_event(event)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("realtime_redis_listener_error")
            await asyncio.sleep(1.0)
        finally:
            if pubsub is not None:
                try:
                    await pubsub.unsubscribe(REDIS_EVENTS_CHANNEL)
                    await pubsub.aclose()  # type: ignore[no-untyped-call]
                except Exception:
                    pass
