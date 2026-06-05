from __future__ import annotations

from app.modules.audit.sanitize import sanitize_audit_payload


def test_sanitize_removes_authorization_and_token() -> None:
    payload = {
        "authorization": "Bearer secret",
        "token": "abc",
        "meta": {"ok": True},
    }
    cleaned = sanitize_audit_payload(payload)
    assert "authorization" not in cleaned
    assert "token" not in cleaned
    assert cleaned["meta"]["ok"] is True


def test_sanitize_removes_telegram_user_id() -> None:
    payload = {
        "before": {"telegram_user_id": 123, "full_name": "A"},
        "after": {"telegram_user_id": 456, "full_name": "B"},
    }
    cleaned = sanitize_audit_payload(payload)
    assert "telegram_user_id" not in cleaned["before"]
    assert "telegram_user_id" not in cleaned["after"]
    assert cleaned["before"]["full_name"] == "A"
