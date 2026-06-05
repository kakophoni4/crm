from __future__ import annotations

import pytest
import structlog

from app.shared.logging import MASKED_KEYS, mask_event_dict, mask_sensitive_data


def test_mask_event_dict_masks_sensitive_keys() -> None:
    event = {
        "telegram_user_id": 12345,
        "password": "secret",
        "inbound_secret": "in",
        "outbound_secret": "out",
        "authorization": "Bearer x",
        "token": "tok",
        "safe": "visible",
        "nested": {"password": "nested-secret", "ok": True},
    }
    masked = mask_event_dict(event)
    assert masked["safe"] == "visible"
    assert masked["nested"]["ok"] is True
    for key in MASKED_KEYS:
        if key in event:
            assert masked[key] == "***"
    assert masked["nested"]["password"] == "***"


def test_mask_sensitive_data_respects_log_pii_mask_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.shared import logging as logging_module

    monkeypatch.setattr(logging_module.settings, "log_pii_mask", False)
    event_dict: structlog.types.EventDict = {"password": "plain", "event": "test"}
    result = mask_sensitive_data(None, "", event_dict)
    assert result["password"] == "plain"

    monkeypatch.setattr(logging_module.settings, "log_pii_mask", True)
    result = mask_sensitive_data(None, "", dict(event_dict))
    assert result["password"] == "***"


def test_mask_sensitive_data_processor_on_event_dict() -> None:
    event_dict: structlog.types.EventDict = {
        "event": "probe",
        "telegram_user_id": 999,
        "password": "pw",
        "token": "t",
    }
    masked = mask_sensitive_data(None, "", dict(event_dict))
    assert masked["telegram_user_id"] == "***"
    assert masked["password"] == "***"
    assert masked["token"] == "***"
    assert masked["event"] == "probe"
