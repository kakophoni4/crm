from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from app.realtime.hub import WsClient
from app.realtime.scope import WsScope
from app.modules.db.models.enums import UserRole

pytestmark = pytest.mark.asyncio(loop_scope="function")


def _client() -> WsClient:
    scope = WsScope(
        user_id=1,
        role=UserRole.USER,
        department_id=None,
        group_id=None,
        actor_group_ids=frozenset(),
        department_group_ids=frozenset(),
        visible_user_ids=frozenset({1}),
    )
    return WsClient(websocket=MagicMock(), ws_scope=scope)


async def test_enqueue_drops_oldest_on_overflow() -> None:
    client = _client()
    client.accepts_outbound = True
    client.outbound_queue = asyncio.Queue(maxsize=2)

    client.enqueue_text("first")
    client.enqueue_text("second")
    client.enqueue_text("third")

    assert client.outbound_queue.get_nowait() == "second"
    assert client.outbound_queue.get_nowait() == "third"
    with pytest.raises(asyncio.QueueEmpty):
        client.outbound_queue.get_nowait()


async def test_enqueue_ignored_after_unsubscribe_flag() -> None:
    client = _client()
    client.accepts_outbound = False

    client.enqueue_text("ignored")

    assert client.outbound_queue.empty()
