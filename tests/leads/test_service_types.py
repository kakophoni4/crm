from __future__ import annotations

import pytest

from app.modules.leads.service_types import (
    ALL_SERVICE_TYPES,
    DEFAULT_BOT_SERVICE_TYPES,
    normalize_service_types,
)


def test_normalize_service_types_defaults() -> None:
    assert normalize_service_types(None) == list(DEFAULT_BOT_SERVICE_TYPES)
    assert normalize_service_types([]) == list(DEFAULT_BOT_SERVICE_TYPES)


def test_normalize_service_types_dedupes_and_orders_input() -> None:
    assert normalize_service_types(["ОПТ", "Деревья", "ОПТ"]) == ["ОПТ", "Деревья"]


def test_normalize_service_types_rejects_unknown() -> None:
    with pytest.raises(ValueError):
        normalize_service_types(["Стрижка"])


def test_all_service_types_contains_both() -> None:
    assert set(ALL_SERVICE_TYPES) == {"Деревья", "ОПТ"}
