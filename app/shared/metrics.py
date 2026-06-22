from __future__ import annotations

from typing import TYPE_CHECKING, Any

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


def _patch_instrumentator_routing_for_included_router() -> None:
    """Work around FastAPI 0.137+ _IncludedRouter missing `.path` (instrumentator #370)."""

    from prometheus_fastapi_instrumentator import routing as instrumentator_routing
    from starlette.routing import Match, Mount
    from starlette.types import Scope

    if getattr(instrumentator_routing, "_included_router_patch_applied", False):
        return

    def _get_route_name(
        scope: Scope,
        routes: list[Any],
        route_name: str | None = None,
    ) -> str | None:
        for route in routes:
            if hasattr(route, "effective_candidates"):
                match, child_scope, matched_route, route_context = route._match(scope)
                if match == Match.FULL:
                    route_name = (
                        route_context.path
                        if route_context is not None
                        else getattr(matched_route, "path", None)
                    )
                    if route_name is not None:
                        child_scope = {**scope, **child_scope}
                        target_route = (
                            route_context.starlette_route
                            if route_context is not None
                            else matched_route
                        )
                        if isinstance(target_route, Mount) and target_route.routes:
                            child_route_name = _get_route_name(
                                child_scope, target_route.routes, route_name
                            )
                            if child_route_name is None:
                                route_name = None
                            else:
                                route_name = (
                                    child_route_name
                                    if route_name is None
                                    else route_name + child_route_name
                                )
                    return route_name
                if match == Match.PARTIAL and route_name is None:
                    route_name = (
                        route_context.path
                        if route_context is not None
                        else getattr(matched_route, "path", None)
                    )
                    continue

            match, child_scope = route.matches(scope)
            if match == Match.FULL:
                route_name = getattr(route, "path", None)
                child_scope = {**scope, **child_scope}
                if isinstance(route, Mount) and route.routes:
                    child_route_name = _get_route_name(
                        child_scope, route.routes, route_name
                    )
                    if child_route_name is None:
                        route_name = None
                    else:
                        route_name = (
                            child_route_name
                            if route_name is None
                            else route_name + child_route_name
                        )
                return route_name
            if match == Match.PARTIAL and route_name is None:
                route_name = getattr(route, "path", None)
        return None

    instrumentator_routing._get_route_name = _get_route_name
    instrumentator_routing._included_router_patch_applied = True  # type: ignore[attr-defined]


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

    _patch_instrumentator_routing_for_included_router()

    Instrumentator(
        should_group_status_codes=False,
        should_ignore_untemplated=True,
        excluded_handlers=["/metrics", "/healthz", "/readyz"],
    ).instrument(app)


def render_metrics() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST
