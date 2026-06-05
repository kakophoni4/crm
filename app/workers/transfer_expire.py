from __future__ import annotations

import structlog

from app.modules.contacts.transfer_expire import expire_stale_transfers
from app.shared.db import get_session_factory
from app.shared.settings import settings

logger = structlog.get_logger(__name__)


async def transfer_expire_scan(
    _job_type: str = "",
    _payload: dict[str, object] | None = None,
) -> None:
    del _job_type, _payload
    if not settings.ownership_v2:
        return

    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            result = await expire_stale_transfers(session)
            await session.commit()
            if result.expired:
                logger.info("transfer_expire_scan_done", expired=result.expired)
        except Exception:
            await session.rollback()
            raise
