from __future__ import annotations

from app.workers.jobs.queue import register_handler, start_worker, stop_worker
from app.workers.jobs.scheduler import (
    PERIODIC_JOB_TYPE,
    run_periodic_maintenance,
    start_scheduler,
    stop_scheduler,
)


def register_crm_job_workers() -> None:
    register_handler(PERIODIC_JOB_TYPE, run_periodic_maintenance)
    from app.modules.leads.opt.queue import OPT_SUBMIT_JOB_TYPE
    from app.workers.jobs.opt_submit import process_opt_submit_queue
    from app.workers.jobs.sbis_norm_sync import (
        SBIS_NORM_SYNC_JOB_TYPE,
        process_sbis_norm_sync,
    )

    register_handler(OPT_SUBMIT_JOB_TYPE, process_opt_submit_queue)
    register_handler(SBIS_NORM_SYNC_JOB_TYPE, process_sbis_norm_sync)


def start_crm_jobs() -> None:
    import asyncio

    from app.workers.jobs.opt_submit import bootstrap_opt_submit_queue

    register_crm_job_workers()
    start_worker()
    start_scheduler()
    try:
        asyncio.get_running_loop().create_task(
            bootstrap_opt_submit_queue(),
            name="opt-submit-bootstrap",
        )
    except RuntimeError:
        pass


async def stop_crm_jobs() -> None:
    await stop_scheduler()
    await stop_worker()


__all__ = ["start_crm_jobs", "stop_crm_jobs"]
