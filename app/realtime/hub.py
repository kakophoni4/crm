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


@dataclass
class WsClient:
    websocket: WebSocket
    ws_scope: WsScope
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    @property
    def user_id(self) -> int:
        return self.ws_scope.user_id


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
            active = len(self._clients)
            self._clients.clear()
        for _ in range(active):
            ws_connection_closed()
        logger.info("realtime_hub_stopped")

    async def subscribe(self, client: WsClient) -> None:
        async with self._clients_lock:
            if not any(existing is client for existing in self._clients):
                self._clients.append(client)
                ws_connection_opened()

    async def unsubscribe(self, client: WsClient) -> None:
        async with self._clients_lock:
            before = len(self._clients)
            self._clients = [existing for existing in self._clients if existing is not client]
            if len(self._clients) < before:
                ws_connection_closed()

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
            try:
                async with client.send_lock:
                    await client.websocket.send_text(raw)
            except (WebSocketDisconnect, RuntimeError):
                await self.unsubscribe(client)
            except Exception:
                logger.exception(
                    "realtime_ws_send_failed",
                    user_id=client.user_id,
                    topic=event.topic,
                )
                await self.unsubscribe(client)

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
    "RealtimeHub",
    "WsClient",
    "get_hub",
    "reset_hub",
]
