from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import AsyncClient
from httpx_ws import AsyncWebSocketSession
from httpx_ws.transport import ASGIWebSocketTransport

from app.realtime.hub import get_hub, reset_hub
from app.shared.db import get_db
from app.shared.settings import get_settings

pytestmark = pytest.mark.asyncio(loop_scope="function")


async def wait_for_connected(
    ws: AsyncWebSocketSession,
    *,
    timeout: float = 2.0,
) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        message = await ws.receive_json(timeout=max(0.05, remaining))
        if message.get("type") == "connected":
            return message
    msg = "Timed out waiting for WebSocket connected message"
    raise TimeoutError(msg)


async def receive_domain_event(
    ws: AsyncWebSocketSession,
    *,
    timeout: float = 2.0,
) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        message = await ws.receive_json(timeout=max(0.05, remaining))
        msg_type = str(message.get("type", ""))
        if msg_type in {"connected", "ping", "pong"}:
            continue
        return message
    msg = "Timed out waiting for domain WebSocket event"
    raise TimeoutError(msg)


@asynccontextmanager
async def ws_http_client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.shared import db as db_module

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        session_factory = db_module.get_session_factory()
        session = session_factory()
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGIWebSocketTransport(app=app, initial_receive_timeout=5.0)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as http_client:
            yield http_client
    finally:
        app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def realtime_hub() -> AsyncIterator[None]:
    get_settings.cache_clear()
    reset_hub()
    await get_hub().start()
    yield
    await get_hub().stop()
    reset_hub()


@pytest.fixture
def ws_connect_kwargs() -> dict[str, Any]:
    return {"keepalive_ping_interval_seconds": None}
