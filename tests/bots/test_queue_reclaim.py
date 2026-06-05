from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.workers.bots.queue import STREAM_KEY, _reclaim_stale_pending


@pytest.mark.asyncio
async def test_reclaim_stale_pending_calls_xautoclaim() -> None:
    mock_redis = AsyncMock()
    mock_redis.xautoclaim = AsyncMock(return_value=("0-0", [], []))

    with patch("app.workers.bots.queue.get_redis", return_value=mock_redis):
        await _reclaim_stale_pending()

    mock_redis.xautoclaim.assert_awaited_once()
    args = mock_redis.xautoclaim.await_args.args
    assert args[0] == STREAM_KEY
