from __future__ import annotations

from datetime import UTC, datetime

import structlog

from app.modules.storage.repository import StorageRepository
from app.shared.db import get_session_factory

logger = structlog.get_logger(__name__)


async def purge_expired_share_links(_job_type: str, _payload: dict[str, object]) -> None:
    now = datetime.now(UTC)
    session_factory = get_session_factory()
    async with session_factory() as session:
        repo = StorageRepository(session)
        file_ids = await repo.purge_expired_shares(now)
        await session.commit()
        if file_ids:
            logger.info("expired_share_links_revoked", count=len(file_ids))
