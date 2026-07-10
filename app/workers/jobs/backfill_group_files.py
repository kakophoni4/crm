from __future__ import annotations

from typing import Any

import structlog

from app.shared.db import get_session_factory
from app.shared.redis import get_redis

logger = structlog.get_logger(__name__)

_BACKFILL_LOCK_KEY = "crm:storage:group-files:backfill"
_BACKFILL_LOCK_TTL_SECONDS = 3600


async def backfill_group_chat_files_job(_job_type: str, _payload: dict[str, Any]) -> None:
    redis = get_redis()
    acquired = await redis.set(_BACKFILL_LOCK_KEY, "1", nx=True, ex=_BACKFILL_LOCK_TTL_SECONDS)
    if not acquired:
        return

    session_factory = get_session_factory()
    async with session_factory() as session:
        from app.modules.storage.indexing import backfill_group_chat_files

        count = await backfill_group_chat_files(session, limit=500)
        await session.commit()
        if count:
            logger.info("group_chat_files_backfill_job_done", indexed_messages=count)
