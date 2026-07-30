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
PULL_REQUEST_KEY = "crm:sbis_norm:pull_requested"
RECEIPTS_PULL_REQUEST_KEY = "crm:sbis_receipts:pull_requested"


def _sync_mode() -> str:
    mode = (get_settings().sbis_norm_sync_mode or "agent").strip().lower()
    return mode if mode in {"agent", "direct"} else "agent"


async def request_sbis_norm_pull(*, reason: str = "manual") -> None:
    """Signal kali pull-agent that a sync was requested (UI button / schedule)."""
    redis = get_redis()
    await redis.set(PULL_REQUEST_KEY, reason)
    logger.info("sbis_norm_pull_requested", reason=reason)


async def claim_sbis_norm_pull() -> bool:
    """Atomically claim a pending pull request for the external agent."""
    redis = get_redis()
    getdel = getattr(redis, "getdel", None)
    if callable(getdel):
        val = await getdel(PULL_REQUEST_KEY)
    else:
        val = await redis.get(PULL_REQUEST_KEY)
        if val is not None:
            await redis.delete(PULL_REQUEST_KEY)
    return val is not None


async def request_sbis_receipts_pull(*, reason: str = "manual") -> None:
    redis = get_redis()
    await redis.set(RECEIPTS_PULL_REQUEST_KEY, reason)
    logger.info("sbis_receipts_pull_requested", reason=reason)


async def claim_sbis_receipts_pull() -> bool:
    redis = get_redis()
    getdel = getattr(redis, "getdel", None)
    if callable(getdel):
        val = await getdel(RECEIPTS_PULL_REQUEST_KEY)
    else:
        val = await redis.get(RECEIPTS_PULL_REQUEST_KEY)
        if val is not None:
            await redis.delete(RECEIPTS_PULL_REQUEST_KEY)
    return val is not None


async def process_sbis_norm_sync(_job_type: str, _payload: dict[str, object]) -> None:
    del _job_type, _payload
    settings = get_settings()
    mode = _sync_mode()
    if mode == "agent":
        await request_sbis_norm_pull(reason="worker")
        logger.info("sbis_norm_sync_job_delegated_to_agent")
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
    """Enqueue / request pull. Manual UI sync uses force=True (works even if auto off)."""
    settings = get_settings()
    mode = _sync_mode()

    if force:
        if mode == "agent":
            await request_sbis_norm_pull(reason="manual")
            return
        # direct + manual: fall through to enqueue even when auto-sync disabled
    elif not settings.sbis_norm_sync_enabled:
        return

    if mode == "agent":
        # Periodic auto: set the same flag the kali agent polls.
        if not settings.sbis_norm_sync_enabled:
            return
        redis = get_redis()
        ttl = max(int(settings.sbis_norm_sync_interval_seconds), 60)
        acquired = await redis.set(_SCHEDULE_KEY, "1", nx=True, ex=ttl)
        if not acquired:
            return
        await request_sbis_norm_pull(reason="schedule")
        logger.info("sbis_norm_sync_scheduled_agent", interval_seconds=ttl)
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
