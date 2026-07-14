from __future__ import annotations

import structlog

from app.modules.notifications.service import scan_staff_notification_escalations
from app.shared.db import get_session_factory
from app.shared.settings import settings

logger = structlog.get_logger(__name__)


async def staff_notifications_scan(
    _job_type: str = "",
    _payload: dict[str, object] | None = None,
) -> None:
    del _job_type, _payload
    if not settings.ownership_v2:
        return

    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            counts = await scan_staff_notification_escalations(session)
            await session.commit()
            if any(counts.values()):
                logger.info("staff_notifications_scan_done", **counts)
        except Exception:
            await session.rollback()
            raise
