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

    register_handler(OPT_SUBMIT_JOB_TYPE, process_opt_submit_queue)


def start_crm_jobs() -> None:
    register_crm_job_workers()
    start_worker()
    start_scheduler()


async def stop_crm_jobs() -> None:
    await stop_scheduler()
    await stop_worker()


__all__ = ["start_crm_jobs", "stop_crm_jobs"]
