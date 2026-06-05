from __future__ import annotations

import asyncio
import contextlib
import json
import time
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.contacts.scope_loader import ScopeLoader
from app.modules.db.models.enums import UserRole
from app.realtime.auth import consume_ws_ticket
from app.realtime.hub import WsClient, get_hub
from app.realtime.scope import WsScope
from app.shared.db import get_session_factory
from app.shared.exceptions import AuthenticationRequired
from app.shared.redis import get_redis
from app.shared.settings import get_settings

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["realtime"])

_WS_CLOSE_POLICY = 4401


async def _load_ws_scope(user_id: int, role: str) -> WsScope:
    session_factory = get_session_factory()
    session: AsyncSession = session_factory()
    try:
        from app.modules.auth.repository import AuthRepository

        repo = AuthRepository(session)
        user = await repo.get_user_by_id(user_id)
        if user is None:
            raise AuthenticationRequired(message="User not found")
        ctx = await ScopeLoader(session).load(user)
        return WsScope.from_context(ctx)
    finally:
        await session.close()


@router.websocket("/api/v1/ws")
@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    ticket: Annotated[str, Query()],
) -> None:
    settings = get_settings()
    redis = get_redis()
    hub = get_hub()

    try:
        claims = await consume_ws_ticket(redis, ticket)
    except AuthenticationRequired:
        await websocket.close(code=_WS_CLOSE_POLICY, reason="authentication_required")
        return

    user_id = int(claims["user_id"])
    role = UserRole(str(claims["role"]))
    department_id = claims.get("department_id")
    if department_id is not None:
        department_id = int(department_id)

    provisional_scope = WsScope(
        user_id=user_id,
        role=role,
        department_id=department_id,
        group_id=None,
        department_group_ids=frozenset(),
        visible_user_ids=frozenset({user_id}),
    )

    await websocket.accept()
    await websocket.send_json(hub.connected_message(user_id))

    client = WsClient(websocket=websocket, ws_scope=provisional_scope)
    await hub.subscribe(client)

    idle_seconds = float(settings.ws_idle_timeout_seconds)
    heartbeat_seconds = float(settings.ws_heartbeat_interval_seconds)
    last_client_activity = time.monotonic()
    stop = asyncio.Event()

    async def _enrich_scope() -> None:
        try:
            client.ws_scope = await _load_ws_scope(user_id, role.value)
        except AuthenticationRequired:
            stop.set()

    enrich_task = asyncio.create_task(_enrich_scope())

    async def _idle_watchdog() -> None:
        nonlocal last_client_activity
        while not stop.is_set():
            await asyncio.sleep(min(1.0, idle_seconds / 4))
            if time.monotonic() - last_client_activity >= idle_seconds:
                stop.set()
                break

    async def _heartbeat_sender() -> None:
        while not stop.is_set():
            await asyncio.sleep(heartbeat_seconds)
            if stop.is_set():
                break
            try:
                async with client.send_lock:
                    await websocket.send_json({"type": "ping"})
            except (WebSocketDisconnect, RuntimeError):
                stop.set()
                break

    async def _reader() -> None:
        nonlocal last_client_activity
        while not stop.is_set():
            try:
                raw = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=idle_seconds,
                )
            except TimeoutError:
                if time.monotonic() - last_client_activity >= idle_seconds:
                    stop.set()
                    with contextlib.suppress(RuntimeError):
                        await websocket.close(code=status.WS_1000_NORMAL_CLOSURE)
                    break
                continue
            except WebSocketDisconnect:
                stop.set()
                break

            last_client_activity = time.monotonic()
            try:
                msg: dict[str, Any] = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if msg.get("type") == "ping":
                async with client.send_lock:
                    await websocket.send_json({"type": "pong"})

    watchdog_task = asyncio.create_task(_idle_watchdog())
    heartbeat_task = asyncio.create_task(_heartbeat_sender())
    reader_task = asyncio.create_task(_reader())

    try:
        await stop.wait()
    finally:
        stop.set()
        enrich_task.cancel()
        for task in (watchdog_task, heartbeat_task, reader_task, enrich_task):
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        await hub.unsubscribe(client)
        with contextlib.suppress(RuntimeError):
            await websocket.close(code=status.WS_1000_NORMAL_CLOSURE)
