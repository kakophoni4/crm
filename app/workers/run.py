from __future__ import annotations

import asyncio
import contextlib
import signal
import sys

import structlog

from app.shared.logging import configure_logging
from app.shared.redis import close_redis
from app.shared.settings import get_settings
from app.shared.worker_health import start_worker_heartbeat, stop_worker_heartbeat
from app.workers.bots import register_bot_workers
from app.workers.bots import start_worker as start_bots_worker
from app.workers.bots.queue import stop_worker as stop_bots_worker
from app.workers.jobs import start_crm_jobs, stop_crm_jobs

logger = structlog.get_logger(__name__)


async def _run() -> None:
    configure_logging()
    get_settings()
    register_bot_workers()
    start_bots_worker()
    start_crm_jobs()
    start_worker_heartbeat()
    logger.info("crm_worker_started")
    stop = asyncio.Event()

    def _handle_sig(*_args: object) -> None:
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, _handle_sig)

    await stop.wait()
    await stop_worker_heartbeat()
    await stop_crm_jobs()
    await stop_bots_worker()
    await close_redis()
    logger.info("crm_worker_stopped")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(_run())
