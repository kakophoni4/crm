from __future__ import annotations

import contextvars
import os
import time
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

REQUEST_ID_HEADER = "X-Request-Id"
REQUEST_ID_CTX: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id",
    default=None,
)

_CROCKFORD_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def generate_ulid() -> str:
    """Generate a 26-character Crockford Base32 ULID."""
    timestamp_ms = int(time.time() * 1000)
    time_chars: list[str] = []
    ts = timestamp_ms
    for _ in range(10):
        time_chars.append(_CROCKFORD_ALPHABET[ts & 0x1F])
        ts >>= 5
    time_part = "".join(reversed(time_chars))

    random_bytes = os.urandom(10)
    random_int = int.from_bytes(random_bytes, "big")
    random_chars: list[str] = []
    value = random_int
    for _ in range(16):
        random_chars.append(_CROCKFORD_ALPHABET[value & 0x1F])
        value >>= 5
    random_part = "".join(reversed(random_chars))

    return time_part + random_part


def get_request_id() -> str | None:
    return REQUEST_ID_CTX.get()


def set_request_id(request_id: str) -> contextvars.Token[str | None]:
    return REQUEST_ID_CTX.set(request_id)


def reset_request_id(token: contextvars.Token[str | None]) -> None:
    REQUEST_ID_CTX.reset(token)


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        incoming = request.headers.get(REQUEST_ID_HEADER)
        request_id = incoming.strip() if incoming and incoming.strip() else generate_ulid()
        token = set_request_id(request_id)
        try:
            response = await call_next(request)
        finally:
            reset_request_id(token)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
