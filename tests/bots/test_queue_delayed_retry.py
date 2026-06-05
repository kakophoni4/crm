from __future__ import annotations

import json
import time
from unittest.mock import AsyncMock, patch

import pytest

from app.workers.bots.queue import DELAYED_KEY, STREAM_KEY, enqueue


@pytest.mark.asyncio
async def test_enqueue_with_delay_uses_sorted_set() -> None:
    mock_redis = AsyncMock()
    mock_redis.zadd = AsyncMock()
    mock_redis.xadd = AsyncMock()

    with patch("app.workers.bots.queue.get_redis", return_value=mock_redis):
        await enqueue("dispatch_outbound", {"outbound_log_id": 1}, delay_seconds=30)

    mock_redis.zadd.assert_awaited_once()
    mock_redis.xadd.assert_not_awaited()
    args, _kwargs = mock_redis.zadd.await_args
    assert args[0] == DELAYED_KEY
    member = next(iter(args[1]))
    parsed = json.loads(member.decode("utf-8"))
    assert parsed["type"] == "dispatch_outbound"
    assert parsed["payload"]["outbound_log_id"] == 1
    score = args[1][member]
    assert score >= time.time() + 29


@pytest.mark.asyncio
async def test_enqueue_immediate_uses_stream() -> None:
    mock_redis = AsyncMock()
    mock_redis.zadd = AsyncMock()
    mock_redis.xadd = AsyncMock()

    with patch("app.workers.bots.queue.get_redis", return_value=mock_redis):
        await enqueue("process_bot_event", {"event_id": "evt-1"})

    mock_redis.xadd.assert_awaited_once()
    assert mock_redis.xadd.await_args.args[0] == STREAM_KEY
