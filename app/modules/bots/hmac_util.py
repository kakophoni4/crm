from __future__ import annotations

import hashlib
import hmac
from urllib.parse import urlparse


def body_sha256_hex(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def sign_inbound(event_id: str, timestamp: str, body: bytes, secret: str) -> str:
    canonical = f"{event_id}.{timestamp}.{body_sha256_hex(body)}"
    return hmac.new(secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_inbound(
    event_id: str,
    timestamp: str,
    body: bytes,
    secret: str,
    signature: str,
) -> bool:
    expected = sign_inbound(event_id, timestamp, body, secret)
    return hmac.compare_digest(expected, signature.strip().removeprefix("sha256="))


def sign_outbound(method: str, path: str, timestamp: str, body: bytes, secret: str) -> str:
    canonical = f"{method.upper()}\n{path}\n{timestamp}\n{body_sha256_hex(body)}"
    digest = hmac.new(secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def verify_outbound(
    method: str,
    path: str,
    timestamp: str,
    body: bytes,
    secret: str,
    signature: str,
) -> bool:
    expected = sign_outbound(method, path, timestamp, body, secret)
    got = signature.strip()
    if not got.startswith("sha256="):
        got = f"sha256={got}"
    return hmac.compare_digest(expected, got)


def outbound_path_from_url(url: str) -> str:
    parsed = urlparse(url)
    return parsed.path or "/"


def sign_health_get(url: str, timestamp: str, secret: str) -> str:
    path = outbound_path_from_url(url)
    return sign_outbound("GET", path, timestamp, b"", secret)
