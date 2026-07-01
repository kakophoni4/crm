from __future__ import annotations

SERVICE_TYPE_TREES = "Деревья"
SERVICE_TYPE_OPT = "ОПТ"

ALL_SERVICE_TYPES: tuple[str, ...] = (SERVICE_TYPE_TREES, SERVICE_TYPE_OPT)
DEFAULT_BOT_SERVICE_TYPES: tuple[str, ...] = ALL_SERVICE_TYPES


def normalize_service_types(values: list[str] | None) -> list[str]:
    if not values:
        return list(DEFAULT_BOT_SERVICE_TYPES)
    allowed = set(ALL_SERVICE_TYPES)
    normalized: list[str] = []
    for value in values:
        text = str(value).strip()
        if text in allowed and text not in normalized:
            normalized.append(text)
    if not normalized:
        raise ValueError("service_types must include at least one known service type")
    return normalized
