from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from app.modules.analytics.router import router as analytics_router
from app.modules.accounting.router import router as accounting_router
from app.modules.auth.router import router as auth_router
from app.modules.bots.router import router as bots_router
from app.modules.chats.router import router as chats_router
from app.modules.contacts.contact_transfers_router import router as contact_transfers_router
from app.modules.contacts.router import router as contacts_router
from app.modules.departments.router import router as departments_router
from app.modules.files.router import bot_outbound_router
from app.modules.files.router import router as files_router
from app.modules.groups.router import router as groups_router
from app.modules.leads.router import router as leads_router
from app.modules.leads.opt.router import router as leads_opt_router
from app.modules.search.router import router as search_router
from app.modules.storage.public_router import router as storage_public_router
from app.modules.storage.router import router as storage_router
from app.modules.statuses.router import router as statuses_router
from app.modules.tasks.router import router as tasks_router
from app.modules.telephony.router import router as telephony_router
from app.modules.users.router import router as users_router
from app.modules.users.user_deletion_router import router as user_deletion_requests_router
from app.realtime.auth import router as realtime_auth_router
from app.realtime.hub import get_hub, reset_hub
from app.realtime.router import router as realtime_router
from app.shared.db import db_ping, dispose_engine
from app.shared.exceptions import register_exception_handlers
from app.shared.logging import configure_logging
from app.shared.metrics import (
    refresh_redis_stream_gauges,
    render_metrics,
    setup_prometheus_instrumentation,
)
from app.shared.redis import close_redis, redis_ping
from app.shared.request_id import RequestIdMiddleware
from app.shared.sentry import init_sentry
from app.shared.settings import settings
from app.shared.worker_health import (
    start_worker_heartbeat,
    stop_worker_heartbeat,
    worker_ping,
)
from app.workers.bots import register_bot_workers, start_worker
from app.workers.bots.queue import stop_worker
from app.workers.jobs import start_crm_jobs, stop_crm_jobs

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> Any:
    init_sentry(settings)
    if not await db_ping():
        logger.warning("database_unavailable_at_startup")
    if not await redis_ping():
        logger.warning("redis_unavailable_at_startup")
    if settings.workers_in_api:
        register_bot_workers()
        start_worker()
        start_crm_jobs()
        start_worker_heartbeat()
    hub = get_hub()
    await hub.start()
    yield
    await hub.stop()
    reset_hub()
    if settings.workers_in_api:
        await stop_worker_heartbeat()
        await stop_crm_jobs()
        await stop_worker()
    await close_redis()
    await dispose_engine()


def create_app() -> FastAPI:
    configure_logging()

    app = FastAPI(
        title="CRM Chat Center",
        version="0.1.0",
        openapi_url="/api/openapi.json",
        docs_url="/api/docs",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestIdMiddleware)
    register_exception_handlers(app)
    setup_prometheus_instrumentation(app)
    app.include_router(auth_router)
    app.include_router(departments_router)
    app.include_router(users_router)
    app.include_router(user_deletion_requests_router)
    app.include_router(realtime_auth_router)
    app.include_router(realtime_router)
    app.include_router(contacts_router)
    app.include_router(leads_router)
    app.include_router(leads_opt_router)
    app.include_router(contact_transfers_router)
    app.include_router(groups_router)
    app.include_router(chats_router)
    app.include_router(search_router)
    app.include_router(statuses_router)
    app.include_router(bots_router)
    app.include_router(telephony_router)
    app.include_router(files_router)
    app.include_router(bot_outbound_router)
    app.include_router(storage_router)
    app.include_router(storage_public_router)
    app.include_router(tasks_router)
    app.include_router(analytics_router)
    app.include_router(accounting_router)

    def _health_checks(
        db_ok: bool,
        redis_ok: bool,
        worker_ok: bool | None,
    ) -> dict[str, bool | None]:
        return {"db": db_ok, "redis": redis_ok, "worker": worker_ok}

    def _health_status(db_ok: bool, redis_ok: bool, worker_ok: bool | None) -> str:
        core_ok = db_ok and redis_ok
        worker_required = worker_ok is not None
        if worker_required:
            return "ok" if core_ok and worker_ok else "degraded"
        return "ok" if core_ok else "degraded"

    async def _probe_worker() -> bool | None:
        if not settings.workers_in_api:
            return None
        return await worker_ping()

    @app.get("/healthz")
    async def healthz() -> dict[str, Any]:
        db_ok = await db_ping()
        redis_ok = await redis_ping()
        worker_ok = await _probe_worker()
        return {
            "status": _health_status(db_ok, redis_ok, worker_ok),
            "checks": _health_checks(db_ok, redis_ok, worker_ok),
        }

    @app.get("/readyz")
    async def readyz() -> JSONResponse:
        db_ok = await db_ping()
        redis_ok = await redis_ping()
        worker_ok = await _probe_worker()
        checks = _health_checks(db_ok, redis_ok, worker_ok)
        ready = _health_status(db_ok, redis_ok, worker_ok) == "ok"
        body = {
            "status": "ready" if ready else "not_ready",
            "checks": checks,
        }
        return JSONResponse(status_code=200 if ready else 503, content=body)

    @app.get("/metrics")
    async def metrics() -> Response:
        if not settings.metrics_enabled:
            return Response(status_code=404)
        await refresh_redis_stream_gauges()
        body, content_type = render_metrics()
        return Response(content=body, media_type=content_type)

    @app.get("/share")
    async def redirect_public_share_upload() -> RedirectResponse:
        base = settings.app_public_base_url.rstrip("/")
        return RedirectResponse(url=f"{base}/share", status_code=307)

    @app.get("/share/{token}")
    async def redirect_public_share_download(token: str) -> RedirectResponse:
        base = settings.app_public_base_url.rstrip("/")
        return RedirectResponse(url=f"{base}/share/{token}", status_code=307)

    return app


app = create_app()
