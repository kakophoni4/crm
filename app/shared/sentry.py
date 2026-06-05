from __future__ import annotations

from typing import Any

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration
from sentry_sdk.types import Event, Hint

from app.shared.logging import mask_event_dict
from app.shared.settings import Settings

_PII_EVENT_KEYS = frozenset(
    {
        "telegram_user_id",
        "password",
        "password_hash",
        "inbound_secret",
        "outbound_secret",
        "authorization",
        "token",
        "secret",
        "signature",
    }
)


def _scrub_value(key: str, value: object) -> object:
    if key.lower() in _PII_EVENT_KEYS:
        return "[Filtered]"
    if isinstance(value, dict):
        return _scrub_mapping(value)
    if isinstance(value, list):
        return [_scrub_value(key, item) for item in value]
    return value


def _scrub_mapping(data: dict[str, Any]) -> dict[str, Any]:
    scrubbed: dict[str, Any] = {}
    for key, value in data.items():
        if key.lower() in _PII_EVENT_KEYS:
            scrubbed[key] = "[Filtered]"
        elif isinstance(value, dict):
            scrubbed[key] = _scrub_mapping(value)
        elif isinstance(value, list):
            scrubbed[key] = [
                _scrub_mapping(item) if isinstance(item, dict) else _scrub_value(key, item)
                for item in value
            ]
        else:
            scrubbed[key] = value
    return scrubbed


def before_send(event: Event, hint: Hint) -> Event | None:
    del hint
    extra = event.get("extra")
    if isinstance(extra, dict):
        event["extra"] = _scrub_mapping(extra)
    contexts = event.get("contexts")
    if isinstance(contexts, dict):
        event["contexts"] = _scrub_mapping(contexts)
    request = event.get("request")
    if isinstance(request, dict):
        headers = request.get("headers")
        if isinstance(headers, dict):
            request["headers"] = mask_event_dict(headers)
        data = request.get("data")
        if isinstance(data, dict):
            request["data"] = mask_event_dict(data)
        event["request"] = request
    return event


def init_sentry(settings: Settings) -> None:
    if not settings.sentry_dsn:
        return
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.sentry_environment or settings.app_env,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        send_default_pii=False,
        before_send=before_send,
        integrations=[
            StarletteIntegration(),
            FastApiIntegration(),
        ],
    )


def capture_exception(exc: BaseException) -> None:
    if not sentry_sdk.is_initialized():
        return
    sentry_sdk.capture_exception(exc)
