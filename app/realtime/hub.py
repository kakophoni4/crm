from __future__ import annotations

import asyncio
import contextlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect

from app.realtime.events import Event, redis_events_listener
from app.realtime.scope import WsScope, event_visible
from app.shared.metrics import ws_connection_closed, ws_connection_opened

logger = structlog.get_logger(__name__)

# Per-client cap; fanout uses put_nowait so a slow consumer cannot block others.
OUTBOUND_QUEUE_MAXSIZE = 256

_GAP_FRAME = json.dumps(
    {
        "type": "realtime.gap",
        "topic": "realtime.gap",
        "payload": {"reason": "slow_consumer"},
    },
)


@dataclass
class WsClient:
    websocket: WebSocket
    ws_scope: WsScope
    outbound_queue: asyncio.Queue[str] = field(
        default_factory=lambda: asyncio.Queue(maxsize=OUTBOUND_QUEUE_MAXSIZE),
    )
    accepts_outbound: bool = False
    gap_pending: bool = False
    _sender_task: asyncio.Task[None] | None = field(default=None, repr=False, compare=False)

    @property
    def user_id(self) -> int:
        return self.ws_scope.user_id

    def enqueue_text(self, text: str) -> None:
        """Non-blocking enqueue; on overflow drop oldest and mark gap for resync."""
        if not self.accepts_outbound:
            return
        queue = self.outbound_queue
        try:
            queue.put_nowait(text)
        except asyncio.QueueFull:
            # Slow consumer: shed stale messages instead of blocking fanout.
            with contextlib.suppress(asyncio.QueueEmpty):
                queue.get_nowait()
            self.gap_pending = True
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(text)

    def enqueue_json(self, payload: dict[str, Any]) -> None:
        self.enqueue_text(json.dumps(payload, default=str))


class RealtimeHub:
    def __init__(self) -> None:
        self._clients: list[WsClient] = []
        self._clients_lock = asyncio.Lock()
        self._stopped = asyncio.Event()
        self._listener_task: asyncio.Task[None] | None = None

    @property
    def is_running(self) -> bool:
        return self._listener_task is not None and not self._listener_task.done()

    async def start(self) -> None:
        if self.is_running:
            return
        self._stopped.clear()
        self._listener_task = asyncio.create_task(
            redis_events_listener(on_event=self._on_event, stopped=self._stopped),
            name="realtime_redis_listener",
        )
        logger.info("realtime_hub_started")

    async def stop(self) -> None:
        self._stopped.set()
        if self._listener_task is not None:
            self._listener_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._listener_task
            self._listener_task = None
        async with self._clients_lock:
            clients = list(self._clients)
            self._clients.clear()
        for client in clients:
            client.accepts_outbound = False
            await self._stop_client_sender(client)
        for _ in range(len(clients)):
            ws_connection_closed()
        logger.info("realtime_hub_stopped")

    async def subscribe(self, client: WsClient) -> None:
        start_sender = False
        async with self._clients_lock:
            if not any(existing is client for existing in self._clients):
                client.accepts_outbound = True
                self._clients.append(client)
                ws_connection_opened()
                start_sender = True
        if start_sender:
            await self._start_client_sender(client)

    async def unsubscribe(self, client: WsClient) -> None:
        removed = False
        async with self._clients_lock:
            before = len(self._clients)
            self._clients = [existing for existing in self._clients if existing is not client]
            if len(self._clients) < before:
                removed = True
                client.accepts_outbound = False
                ws_connection_closed()
        if not removed:
            return
        sender_task = client._sender_task
        if sender_task is asyncio.current_task():
            client._sender_task = None
            self._drain_outbound_queue(client)
            return
        await self._stop_client_sender(client)

    async def _start_client_sender(self, client: WsClient) -> None:
        if not client.accepts_outbound:
            return
        if client._sender_task is not None and not client._sender_task.done():
            return
        client._sender_task = asyncio.create_task(
            self._client_sender(client),
            name=f"realtime_ws_sender_{client.user_id}",
        )

    async def _stop_client_sender(self, client: WsClient) -> None:
        task = client._sender_task
        client._sender_task = None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._drain_outbound_queue(client)

    @staticmethod
    def _drain_outbound_queue(client: WsClient) -> None:
        while True:
            try:
                client.outbound_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    async def _client_sender(self, client: WsClient) -> None:
        try:
            while client.accepts_outbound:
                if client.gap_pending:
                    client.gap_pending = False
                    try:
                        await client.websocket.send_text(_GAP_FRAME)
                    except (WebSocketDisconnect, RuntimeError):
                        await self.unsubscribe(client)
                        return
                    except Exception:
                        logger.exception(
                            "realtime_ws_gap_send_failed",
                            user_id=client.user_id,
                        )
                        await self.unsubscribe(client)
                        return
                text = await client.outbound_queue.get()
                if not client.accepts_outbound:
                    break
                try:
                    await client.websocket.send_text(text)
                except (WebSocketDisconnect, RuntimeError):
                    await self.unsubscribe(client)
                    return
                except Exception:
                    logger.exception(
                        "realtime_ws_send_failed",
                        user_id=client.user_id,
                    )
                    await self.unsubscribe(client)
                    return
        except asyncio.CancelledError:
            raise

    async def _on_event(self, event: Event) -> None:
        await self._fanout(event)

    async def _fanout(self, event: Event) -> None:
        async with self._clients_lock:
            clients = list(self._clients)

        message = {
            "type": event.topic,
            "topic": event.topic,
            "payload": event.payload,
        }
        raw = json.dumps(message, default=str)

        for client in clients:
            if not event_visible(client.ws_scope, event):
                continue
            client.enqueue_text(raw)

    @staticmethod
    def connected_message(user_id: int) -> dict[str, Any]:
        return {
            "type": "connected",
            "user_id": user_id,
            "server_time": datetime.now(UTC).isoformat(),
        }


_hub: RealtimeHub | None = None


def get_hub() -> RealtimeHub:
    global _hub
    if _hub is None:
        _hub = RealtimeHub()
    return _hub


def reset_hub() -> None:
    """Test helper: drop singleton between app restarts."""
    global _hub
    _hub = None


__all__ = [
    "OUTBOUND_QUEUE_MAXSIZE",
    "RealtimeHub",
    "WsClient",
    "get_hub",
    "reset_hub",
]
