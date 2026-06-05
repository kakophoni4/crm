from __future__ import annotations

import logging
from typing import Any

import structlog
from structlog.contextvars import merge_contextvars
from structlog.types import EventDict, Processor, WrappedLogger

from app.shared.request_id import get_request_id
from app.shared.settings import settings

MASKED_KEYS = frozenset(
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
        "payload",
    }
)


def _mask_value(key: str, value: object) -> object:
    if key.lower() in MASKED_KEYS:
        return "***"
    return value


def mask_event_dict(data: dict[str, Any]) -> dict[str, Any]:
    return _mask_dict(data)


def mask_sensitive_data(
    logger: WrappedLogger,
    method_name: str,
    event_dict: EventDict,
) -> EventDict:
    del logger, method_name
    if not settings.log_pii_mask:
        return event_dict
    return _mask_dict(dict(event_dict))


def _mask_dict(data: dict[str, Any]) -> dict[str, Any]:
    masked: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, dict):
            masked[key] = _mask_dict(value)
        elif isinstance(value, list):
            masked[key] = [
                _mask_dict(item) if isinstance(item, dict) else _mask_value(key, item)
                for item in value
            ]
        else:
            masked[key] = _mask_value(key, value)
    return masked


def add_request_id(
    logger: WrappedLogger,
    method_name: str,
    event_dict: EventDict,
) -> EventDict:
    del logger, method_name
    request_id = get_request_id()
    if request_id is not None:
        event_dict.setdefault("request_id", request_id)
    return event_dict


def _shared_processors() -> list[Processor]:
    return [
        merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        add_request_id,
        mask_sensitive_data,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.stdlib.add_logger_name,
        structlog.processors.EventRenamer("event"),
    ]


def configure_logging() -> None:
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    shared = _shared_processors()

    if settings.log_json:
        renderer: Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            *shared,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(log_level)

    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(name).handlers.clear()
        logging.getLogger(name).propagate = True
