from __future__ import annotations

import structlog

from app.modules.contacts.escalation import scan_pending_escalations
from app.shared.db import get_session_factory
from app.shared.settings import settings

logger = structlog.get_logger(__name__)


async def escalation_scan(_job_type: str = "", _payload: dict[str, object] | None = None) -> None:
    del _job_type, _payload
    if not settings.ownership_v2:
        return

    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            result = await scan_pending_escalations(session)
            await session.commit()
            if result.escalated or result.reassigned:
                logger.info(
                    "escalation_scan_done",
                    escalated=result.escalated,
                    reassigned=result.reassigned,
                )
        except Exception:
            await session.rollback()
            raise
