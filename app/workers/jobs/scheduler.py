from __future__ import annotations

import asyncio
import contextlib

import structlog

from app.shared.redis import get_redis
from app.shared.settings import settings
from app.workers.jobs.queue import enqueue

logger = structlog.get_logger(__name__)

PERIODIC_JOB_TYPE = "run_periodic_maintenance"
PERIODIC_INTERVAL_SECONDS = 30
_SCHEDULE_LOCK_KEY = "crm:jobs:periodic:scheduled"
_SCHEDULE_LOCK_TTL_SECONDS = 25

_scheduler_task: asyncio.Task[None] | None = None


_HEALTH_LOCK_KEY = "crm:bots:health_checks:scheduled"


async def run_periodic_maintenance(_job_type: str, _payload: dict[str, object]) -> None:
    from app.modules.leads.opt.queue import schedule_opt_submit_if_pending
    from app.workers.jobs.backfill_group_files import backfill_group_chat_files_job
    from app.workers.jobs.purge_shares import purge_expired_share_links
    from app.workers.jobs.task_reminders import task_due_reminders
    from app.workers.bots.health_check import schedule_all_health_checks
    from app.workers.after_hours import after_hours_scan
    from app.workers.escalation import escalation_scan
    from app.workers.jobs.purge_leads import LEAD_PURGE_JOB_TYPE, purge_expired_leads
    from app.workers.jobs.sbis_norm_sync import schedule_sbis_norm_sync_if_due
    from app.workers.staff_notifications import staff_notifications_scan
    from app.workers.transfer_expire import transfer_expire_scan

    await escalation_scan()
    await after_hours_scan()
    await staff_notifications_scan()
    await transfer_expire_scan()
    await purge_expired_leads(LEAD_PURGE_JOB_TYPE, {})

    redis = get_redis()
    ttl = max(settings.bot_health_check_interval_seconds, 60)
    acquired = await redis.set(_HEALTH_LOCK_KEY, "1", nx=True, ex=ttl)
    if acquired:
        await schedule_all_health_checks()

    await purge_expired_share_links("purge_expired_share_links", {})
    await task_due_reminders("task_due_reminders", {})
    await schedule_opt_submit_if_pending()
    await schedule_sbis_norm_sync_if_due()
    await backfill_group_chat_files_job("backfill_group_chat_files", {})


async def _scheduler_loop() -> None:
    redis = get_redis()
    while True:
        try:
            acquired = await redis.set(
                _SCHEDULE_LOCK_KEY,
                "1",
                nx=True,
                ex=_SCHEDULE_LOCK_TTL_SECONDS,
            )
            if acquired:
                await enqueue(PERIODIC_JOB_TYPE, {})
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("crm_jobs_scheduler_error")
        await asyncio.sleep(PERIODIC_INTERVAL_SECONDS)


def start_scheduler() -> None:
    global _scheduler_task
    # Always run: sbis-norm hourly sync, share purge, opt submit, etc.
    # Ownership-specific jobs no-op when ownership_v2 is off.
    if _scheduler_task is not None and not _scheduler_task.done():
        return
    _scheduler_task = asyncio.create_task(_scheduler_loop(), name="crm-jobs-scheduler")


async def stop_scheduler() -> None:
    global _scheduler_task
    if _scheduler_task is None:
        return
    _scheduler_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await _scheduler_task
    _scheduler_task = None
