from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import select, text

from app.modules.ai.client import call
from app.modules.db.models.ai import AIRequest
from app.shared.db import get_engine, get_session_factory
from app.shared.exceptions import AppError

logger = structlog.get_logger(__name__)


async def process_requests() -> None:
    factory = get_session_factory()
    async with factory() as db:
        rows = (
            await db.execute(
                select(AIRequest.id, AIRequest.path)
                .where(AIRequest.status.in_(["queued", "running"]))
                .order_by(AIRequest.created_at)
                .limit(8)
            )
        ).all()
        # At most one raw archive is materialized at a time in the 512 MB CRM worker.
        ids = []
        archive_selected = False
        for request_id, path in rows:
            if path == "__prepare_export__":
                if archive_selected:
                    continue
                archive_selected = True
            ids.append(request_id)

    import asyncio

    await asyncio.gather(*(process_one(request_id) for request_id in ids))


async def process_one(request_id: Any) -> None:
    factory = get_session_factory()
    # Session advisory lock survives commits and prevents competing workers.
    async with get_engine().connect() as connection, factory() as db:
        locked = await connection.scalar(
            text("SELECT pg_try_advisory_lock(hashtextextended(:id, 0))"), {"id": request_id}
        )
        await connection.commit()
        if not locked:
            return
        try:
            row = await db.get(AIRequest, request_id)
            if row is None:
                return
            if row.status not in ("queued", "running"):
                return
            if row.chat_id is not None:
                from app.modules.db.models.ai import AIChatState
                from app.shared.settings import settings

                state = await db.get(AIChatState, row.chat_id)
                if (
                    not settings.ai_auto_replies_enabled
                    or not state
                    or state.mode == "OFF"
                    or state.revision != row.meta["revision"]
                ):
                    row.status = "obsolete"
                    await db.commit()
                    return
            body, path, admin = row.body, row.path, row.chat_id is None
            await db.commit()
            try:
                if path == "__prepare_export__":
                    import base64

                    from starlette.concurrency import run_in_threadpool

                    from app.modules.ai.imports import prepare

                    result = await run_in_threadpool(prepare, base64.b64decode(body["archive"]))
                    row = await db.get(AIRequest, request_id)
                    if row is None:
                        return
                    row.body, row.result, row.status = {}, result, "succeeded"
                    await db.commit()
                    return
                # Always recover by id before POST, including after a process restart.
                try:
                    _, result = await call("GET", "requests/" + request_id, admin=admin)
                except AppError as exc:
                    if exc.status != 404:
                        raise
                    _, result = await call("POST", path, body=body, admin=admin)
                row = await db.get(AIRequest, request_id)
                if row is None:
                    return
                if "action" in result:
                    row.error = None
                    row.status, row.result = "succeeded", result
                elif result.get("status") == "succeeded":
                    row.status, row.result = "succeeded", result.get("result")
                elif result.get("status") == "failed":
                    row.status, row.error = "failed", result.get("error")
                else:
                    row.status = "running"
                row.updated_at = datetime.now(UTC)
            except AppError as exc:
                row = await db.get(AIRequest, request_id)
                if row is None:
                    return
                row.error = {"code": exc.code, "message": exc.message}
                # Bound recovery; keep the same request id and immutable body.
                row.meta = {**row.meta, "retries": row.meta.get("retries", 0) + 1}
                transient = exc.code == "ai_unreachable" or (
                    exc.status == 429 and row.meta["retries"] <= 3
                )
                if not transient or datetime.now(UTC) - row.created_at > timedelta(hours=2):
                    row.status = "failed"
                if path == "__prepare_export__":
                    row.body = {}
            await db.commit()
        finally:
            # Use the retained physical connection; never return a locked connection to pool.
            if not connection.closed:
                await connection.execute(
                    text("SELECT pg_advisory_unlock(hashtextextended(:id, 0))"), {"id": request_id}
                )
                await connection.commit()


async def ai_loop() -> None:
    import asyncio

    from app.modules.ai.chats import apply_results, dispatch_pending, scan_chats
    from app.modules.ai.client import close_client

    async def replies() -> None:
        while True:
            try:
                await process_requests()
            except Exception:
                logger.exception("ai_requests_worker_error")
            await asyncio.sleep(3)

    async def deliveries() -> None:
        while True:
            try:
                await dispatch_pending()
            except Exception:
                logger.exception("ai_delivery_worker_error")
            await asyncio.sleep(3)

    delivery_task = asyncio.create_task(deliveries())
    task = asyncio.create_task(replies())
    try:
        while True:
            try:
                await scan_chats()
                await apply_results()
            except Exception:
                logger.exception("ai_chats_worker_error")
            await asyncio.sleep(3)
    finally:
        task.cancel()
        delivery_task.cancel()
        import contextlib

        with contextlib.suppress(asyncio.CancelledError):
            await task
        with contextlib.suppress(asyncio.CancelledError):
            await delivery_task
        await close_client()
