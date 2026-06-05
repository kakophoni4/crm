from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from alembic.config import Config

from alembic import command
from app.realtime.hub import get_hub, reset_hub
from app.shared.settings import get_settings


@pytest.fixture(autouse=True)
def _ensure_db_at_head(alembic_config: Config, db_ready: None) -> None:
    """Migration tests may leave DB below head; WS integration needs full schema."""
    del db_ready
    command.upgrade(alembic_config, "head")


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
