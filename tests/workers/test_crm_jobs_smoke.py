from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.workers.jobs import register_crm_job_workers
from app.workers.jobs.queue import enqueue, register_handler


@pytest.mark.asyncio
async def test_enqueue_invokes_registered_handler() -> None:
    handled: list[str] = []

    async def _handler(job_type: str, payload: dict[str, object]) -> None:
        handled.append(f"{job_type}:{payload.get('k')}")

    register_handler("test_job", _handler)
    mock_redis = AsyncMock()
    mock_redis.xadd = AsyncMock()

    with patch("app.workers.jobs.queue.get_redis", return_value=mock_redis):
        await enqueue("test_job", {"k": "v"})

    mock_redis.xadd.assert_awaited_once()
    register_crm_job_workers()
