from __future__ import annotations

from asyncio import Task

from app.workers.jobs.queue import register_handler, start_worker, stop_worker
from app.workers.jobs.scheduler import (
    PERIODIC_JOB_TYPE,
    run_periodic_maintenance,
    start_scheduler,
    stop_scheduler,
)


def register_crm_job_workers() -> None:
    from app.workers.jobs.lawyer_tickets_sync import JOB_TYPE, sync_lawyer_tickets

    register_handler(JOB_TYPE, sync_lawyer_tickets)
    register_handler(PERIODIC_JOB_TYPE, run_periodic_maintenance)
    from app.modules.leads.opt.queue import OPT_SUBMIT_JOB_TYPE
    from app.workers.jobs.opt_submit import process_opt_submit_queue
    from app.workers.jobs.lavok_parser_pull import (
        LAVOK_PARSER_PULL_JOB_TYPE,
        process_lavok_parser_pull,
    )
    from app.workers.jobs.sbis_norm_sync import (
        SBIS_NORM_SYNC_JOB_TYPE,
        process_sbis_norm_sync,
    )

    register_handler(OPT_SUBMIT_JOB_TYPE, process_opt_submit_queue)
    register_handler(SBIS_NORM_SYNC_JOB_TYPE, process_sbis_norm_sync)
    register_handler(LAVOK_PARSER_PULL_JOB_TYPE, process_lavok_parser_pull)


_ai_task: Task[None] | None = None
_task_notifications: Task[None] | None = None
_benik_collection: Task[None] | None = None


def start_crm_jobs() -> None:
    import asyncio

    from app.workers.jobs.lavok_parser_pull import bootstrap_lavok_parser_pull
    from app.workers.jobs.opt_submit import bootstrap_opt_submit_queue
    from app.workers.jobs.sbis_norm_sync import bootstrap_sbis_norm_sync

    global _ai_task, _task_notifications, _benik_collection
    from app.modules.ai.worker import ai_loop

    from app.workers.task_notifications import task_notification_loop
    from app.workers.benik_collection import collection_loop
    register_crm_job_workers()
    start_worker()
    start_scheduler()
    try:
        loop = asyncio.get_running_loop()
        if _benik_collection is None or _benik_collection.done():
            _benik_collection = loop.create_task(collection_loop(), name="benik-collection")
        if _task_notifications is None or _task_notifications.done():
            _task_notifications = loop.create_task(task_notification_loop(), name="task-notifications")
        if _ai_task is None or _ai_task.done():
            _ai_task = loop.create_task(ai_loop(), name="ai-worker")
        loop.create_task(
            bootstrap_opt_submit_queue(),
            name="opt-submit-bootstrap",
        )
        loop.create_task(
            bootstrap_sbis_norm_sync(),
            name="sbis-norm-sync-bootstrap",
        )
        loop.create_task(
            bootstrap_lavok_parser_pull(),
            name="lavok-parser-pull-bootstrap",
        )
    except RuntimeError:
        pass


async def stop_crm_jobs() -> None:
    import asyncio
    import contextlib

    global _ai_task, _task_notifications, _benik_collection
    if _ai_task is not None:
        _ai_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await _ai_task
        _ai_task = None
    if _task_notifications is not None:
        _task_notifications.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await _task_notifications
        _task_notifications = None
    if _benik_collection is not None:
        _benik_collection.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await _benik_collection
        _benik_collection = None
    await stop_scheduler()
    await stop_worker()


__all__ = ["start_crm_jobs", "stop_crm_jobs"]
