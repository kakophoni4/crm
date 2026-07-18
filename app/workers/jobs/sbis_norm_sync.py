from __future__ import annotations

import structlog

from app.modules.accounting.sbis_norm_sync import sync_unsynced_requirements
from app.shared.db import get_session_factory
from app.shared.redis import get_redis
from app.shared.settings import get_settings

logger = structlog.get_logger(__name__)

SBIS_NORM_SYNC_JOB_TYPE = "sbis_norm_sync"
_LOCK_KEY = "crm:sbis_norm:sync:lock"
_LOCK_TTL_SECONDS = 1800
_SCHEDULE_KEY = "crm:sbis_norm:sync:scheduled"


async def process_sbis_norm_sync(_job_type: str, _payload: dict[str, object]) -> None:
    del _job_type, _payload
    settings = get_settings()
    if not settings.sbis_norm_sync_enabled:
        return
    if not settings.sbis_norm_api_base_url.strip():
        return

    redis = get_redis()
    acquired = await redis.set(_LOCK_KEY, "1", nx=True, ex=_LOCK_TTL_SECONDS)
    if not acquired:
        logger.info("sbis_norm_sync_skipped_lock")
        return

    try:
        session_factory = get_session_factory()
        async with session_factory() as session:
            result = await sync_unsynced_requirements(session)
            await session.commit()
        logger.info(
            "sbis_norm_sync_job_done",
            fetched=result.fetched,
            created=result.created,
            existing=result.existing,
            failed=result.failed,
            skipped_non_pdf=result.skipped_non_pdf,
            marked_synced=result.marked_synced,
        )
    except Exception:
        logger.exception("sbis_norm_sync_job_failed")
    finally:
        await redis.delete(_LOCK_KEY)


async def schedule_sbis_norm_sync_if_due(*, force: bool = False) -> None:
    """Enqueue pull when due (default twice/day). Manual UI sync uses force=True."""
    settings = get_settings()
    if not settings.sbis_norm_sync_enabled:
        return
    if not settings.sbis_norm_api_base_url.strip():
        return

    redis = get_redis()
    ttl = max(int(settings.sbis_norm_sync_interval_seconds), 60)
    if force:
        await redis.delete(_SCHEDULE_KEY)
    acquired = await redis.set(_SCHEDULE_KEY, "1", nx=True, ex=ttl)
    if not acquired:
        return

    from app.workers.jobs.queue import enqueue

    await enqueue(SBIS_NORM_SYNC_JOB_TYPE, {})
    logger.info("sbis_norm_sync_scheduled", interval_seconds=ttl, force=force)


async def bootstrap_sbis_norm_sync() -> None:
    """Run first pull soon after worker start, then on the configured interval."""
    await schedule_sbis_norm_sync_if_due(force=True)
