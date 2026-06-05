from __future__ import annotations

from typing import Any

MAX_TITLE_LEN = 500
MAX_LEAD_COMMENT_LEN = 2000
MAX_JSONB_MAP_KEYS = 50
MAX_JSONB_STRING_VALUE_LEN = 2000
MAX_JSONB_NESTING_DEPTH = 2


def _validate_custom_field_value_depth(value: Any, *, depth: int, max_depth: int) -> None:
    if depth > max_depth:
        raise ValueError(f"custom_fields nesting exceeds max depth {max_depth}")
    if isinstance(value, dict):
        for nested in value.values():
            _validate_custom_field_value_depth(nested, depth=depth + 1, max_depth=max_depth)
    elif isinstance(value, list):
        for nested in value:
            _validate_custom_field_value_depth(nested, depth=depth + 1, max_depth=max_depth)


def validate_custom_fields_map(
    value: dict[str, Any] | None,
    *,
    max_keys: int = MAX_JSONB_MAP_KEYS,
    max_str_len: int = MAX_JSONB_STRING_VALUE_LEN,
    max_depth: int = MAX_JSONB_NESTING_DEPTH,
) -> dict[str, Any] | None:
    if value is None:
        return None
    if len(value) > max_keys:
        raise ValueError(f"custom_fields must have at most {max_keys} keys")
    for key, item in value.items():
        if not isinstance(key, str):
            raise ValueError("custom_fields keys must be strings")
        if isinstance(item, str) and len(item) > max_str_len:
            raise ValueError(f"custom_fields[{key!r}] exceeds max length {max_str_len}")
        _validate_custom_field_value_depth(item, depth=1, max_depth=max_depth)
    return value
