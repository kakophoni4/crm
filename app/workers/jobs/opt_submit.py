from __future__ import annotations

import structlog

from app.modules.leads.opt.queue import (
    LOCK_KEY,
    LOCK_TTL_SECONDS,
    OPT_SUBMIT_JOB_TYPE,
    QUEUE_KEY,
    schedule_opt_submit_if_pending,
)
from app.modules.leads.opt.repository import OptOrderRepository
from app.modules.leads.opt.service import OptOrderService
from app.shared.db import get_session_factory
from app.shared.redis import get_redis

logger = structlog.get_logger(__name__)


async def _reconcile_pending_orders() -> None:
    session_factory = get_session_factory()
    async with session_factory() as session:
        repo = OptOrderRepository(session)
        recovered = await repo.recover_stale_submitting(minutes=15)
        queued_ids = await repo.list_ids_by_status("queued")
        await session.commit()

    redis = get_redis()
    for order_id in recovered:
        await redis.rpush(QUEUE_KEY, str(order_id))
    if int(await redis.llen(QUEUE_KEY)) == 0 and queued_ids:
        for order_id in queued_ids:
            await redis.rpush(QUEUE_KEY, str(order_id))

    if recovered:
        logger.warning("opt_submit_recovered_stale", order_ids=recovered)
    if queued_ids and int(await redis.llen(QUEUE_KEY)) > 0:
        logger.info("opt_submit_requeued_pending", count=len(queued_ids))


async def bootstrap_opt_submit_queue() -> None:
    try:
        await _reconcile_pending_orders()
    except Exception:
        logger.exception("opt_submit_bootstrap_failed")
    await schedule_opt_submit_if_pending()


async def process_opt_submit_queue(_job_type: str, _payload: dict[str, object]) -> None:
    del _job_type, _payload
    redis = get_redis()
    acquired = await redis.set(LOCK_KEY, "1", nx=True, ex=LOCK_TTL_SECONDS)
    if not acquired:
        await schedule_opt_submit_if_pending(delay_seconds=5)
        return

    try:
        try:
            await _reconcile_pending_orders()
        except Exception:
            logger.exception("opt_submit_reconcile_failed")

        session_factory = get_session_factory()
        while True:
            raw = await redis.lpop(QUEUE_KEY)
            if raw is None:
                break
            order_id = int(raw.decode() if isinstance(raw, bytes) else raw)
            async with session_factory() as session:
                service = OptOrderService(session)
                try:
                    await service.submit_order_worker(order_id)
                    await session.commit()
                except Exception:
                    await session.rollback()
                    await redis.rpush(QUEUE_KEY, str(order_id))
                    logger.exception("opt_submit_worker_failed", order_id=order_id)
    finally:
        await redis.delete(LOCK_KEY)
        await schedule_opt_submit_if_pending()
