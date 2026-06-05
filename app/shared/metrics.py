from __future__ import annotations

from typing import TYPE_CHECKING

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, generate_latest

if TYPE_CHECKING:
    from fastapi import FastAPI

BOT_EVENTS_INGEST_TOTAL = Counter(
    "bot_events_ingest_total",
    "Bot event ingest results",
    ["status"],
)
BOT_OUTBOUND_TOTAL = Counter(
    "bot_outbound_total",
    "Bot outbound dispatch results",
    ["status"],
)
WS_CONNECTIONS_ACTIVE = Gauge(
    "ws_connections_active",
    "Active WebSocket connections",
)
WS_DISCONNECT_TOTAL = Counter(
    "ws_disconnect_total",
    "WebSocket disconnect events",
)
REDIS_STREAM_PENDING = Gauge(
    "redis_stream_pending",
    "Pending messages in Redis stream consumer groups",
    ["stream"],
)
CRM_LEADS_CREATED_TOTAL = Counter(
    "crm_leads_created_total",
    "Leads created (open lead inserted)",
)
CRM_LEADS_CLOSED_TOTAL = Counter(
    "crm_leads_closed_total",
    "Leads closed",
)

_STREAM_GROUPS: tuple[tuple[str, str], ...] = (
    ("crm:bots:jobs", "bots-workers"),
    ("crm:jobs", "crm-workers"),
)


def inc_bot_events_ingest(status: str) -> None:
    BOT_EVENTS_INGEST_TOTAL.labels(status=status).inc()


def inc_bot_outbound(status: str) -> None:
    BOT_OUTBOUND_TOTAL.labels(status=status).inc()


def inc_lead_created() -> None:
    CRM_LEADS_CREATED_TOTAL.inc()


def inc_lead_closed() -> None:
    CRM_LEADS_CLOSED_TOTAL.inc()


def ws_connection_opened() -> None:
    WS_CONNECTIONS_ACTIVE.inc()


def ws_connection_closed() -> None:
    WS_CONNECTIONS_ACTIVE.dec()
    WS_DISCONNECT_TOTAL.inc()


async def refresh_redis_stream_gauges() -> None:
    from app.shared.redis import get_redis

    redis = get_redis()
    for stream, group in _STREAM_GROUPS:
        pending = 0
        try:
            info = await redis.xpending(stream, group)
            if isinstance(info, dict):
                pending = int(info.get("pending", 0))
            elif isinstance(info, (list, tuple)) and info:
                pending = int(info[0])
        except Exception:
            pending = 0
        REDIS_STREAM_PENDING.labels(stream=stream).set(pending)


def setup_prometheus_instrumentation(app: FastAPI) -> None:
    from prometheus_fastapi_instrumentator import Instrumentator

    from app.shared.settings import settings

    if not settings.metrics_enabled:
        return

    Instrumentator(
        should_group_status_codes=False,
        should_ignore_untemplated=True,
        excluded_handlers=["/metrics", "/healthz", "/readyz"],
    ).instrument(app)


def render_metrics() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST
