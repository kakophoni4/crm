from __future__ import annotations

import pytest

from app.shared.validators.jsonb_limits import validate_custom_fields_map


def test_custom_fields_rejects_depth_over_two() -> None:
    with pytest.raises(ValueError, match="nesting exceeds max depth"):
        validate_custom_fields_map({"a": {"b": {"c": "deep"}}})


def test_custom_fields_allows_depth_two() -> None:
    assert validate_custom_fields_map({"a": {"b": "ok"}}) == {"a": {"b": "ok"}}
