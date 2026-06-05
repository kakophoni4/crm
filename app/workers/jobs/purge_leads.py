from __future__ import annotations

import structlog
from sqlalchemy import delete, func, select

from app.modules.chats.timeutil import utc_now
from app.modules.db.models.lead import Lead
from app.modules.leads.crm_cache import invalidate_contact_crm
from app.shared.db import get_session_factory
from app.shared.redis import get_redis
from app.shared.settings import get_settings

logger = structlog.get_logger(__name__)

LEAD_PURGE_JOB_TYPE = "purge_expired_leads"
_PURGE_BATCH_SIZE = 500


async def purge_expired_leads(_job_type: str, _payload: dict[str, object]) -> None:
    """Delete closed leads past retention_expires_at when LEAD_PURGE_ENABLED=true."""
    del _job_type, _payload
    settings = get_settings()
    now = utc_now()

    session_factory = get_session_factory()
    async with session_factory() as session:
        eligible_stmt = select(func.count()).select_from(Lead).where(
            Lead.closed_at.isnot(None),
            Lead.retention_expires_at.isnot(None),
            Lead.retention_expires_at <= now,
        )
        eligible = int((await session.execute(eligible_stmt)).scalar_one())
        await session.commit()

    if not settings.lead_purge_enabled:
        logger.info(
            "lead_purge_stub",
            eligible_count=eligible,
            deleted_count=0,
            purge_enabled=False,
        )
        return

    if settings.lead_retention_days is None:
        logger.info("lead_purge_skipped", reason="lead_retention_days not set")
        return

    deleted_total = 0
    contact_ids: set[int] = set()
    while True:
        async with session_factory() as session:
            batch_stmt = (
                select(Lead.id, Lead.contact_id)
                .where(
                    Lead.closed_at.isnot(None),
                    Lead.retention_expires_at.isnot(None),
                    Lead.retention_expires_at <= now,
                )
                .limit(_PURGE_BATCH_SIZE)
            )
            rows = (await session.execute(batch_stmt)).all()
            if not rows:
                await session.commit()
                break

            lead_ids = [int(row[0]) for row in rows]
            contact_ids.update(int(row[1]) for row in rows)
            await session.execute(delete(Lead).where(Lead.id.in_(lead_ids)))
            deleted_total += len(lead_ids)
            await session.commit()

        if len(rows) < _PURGE_BATCH_SIZE:
            break

    if contact_ids:
        try:
            redis = get_redis()
            for contact_id in contact_ids:
                await invalidate_contact_crm(redis, contact_id)
        except Exception:
            logger.warning("lead_purge_cache_invalidate_failed", contact_count=len(contact_ids))

    logger.info(
        "lead_purge_completed",
        eligible_count=eligible,
        deleted_count=deleted_total,
        purge_enabled=True,
        message_policy="messages_retained_lead_id_null",
    )
