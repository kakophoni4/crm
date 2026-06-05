from __future__ import annotations

from typing import Any

_SENSITIVE_KEYS = frozenset(
    {
        "telegram_user_id",
        "inbound_secret",
        "outbound_secret",
        "password",
        "password_hash",
        "authorization",
        "token",
    }
)


def sanitize_audit_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not payload:
        return {}

    def _walk(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: _walk(inner) for key, inner in value.items() if key not in _SENSITIVE_KEYS}
        if isinstance(value, list):
            return [_walk(item) for item in value]
        return value

    result = _walk(payload)
    return result if isinstance(result, dict) else {}
