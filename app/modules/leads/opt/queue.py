from __future__ import annotations

import structlog

from app.shared.redis import get_redis

logger = structlog.get_logger(__name__)

QUEUE_KEY = "crm:opt:submit:queue"
LOCK_KEY = "crm:opt:submit:lock"
LOCK_TTL_SECONDS = 600

OPT_SUBMIT_JOB_TYPE = "opt_submit_next"


async def schedule_opt_submit_if_pending(*, delay_seconds: int = 0) -> None:
    """Enqueue CRM job when the Redis list still has order ids to submit."""
    from app.workers.jobs.queue import enqueue

    redis = get_redis()
    if int(await redis.llen(QUEUE_KEY)) > 0:
        await enqueue(OPT_SUBMIT_JOB_TYPE, {}, delay_seconds=delay_seconds)


async def enqueue_opt_submit(order_id: int) -> None:
    from app.workers.jobs.queue import enqueue

    redis = get_redis()
    await redis.rpush(QUEUE_KEY, str(order_id))
    await enqueue(OPT_SUBMIT_JOB_TYPE, {})
    logger.info("opt_submit_enqueued", order_id=order_id)


async def queue_depth() -> int:
    redis = get_redis()
    return int(await redis.llen(QUEUE_KEY))
