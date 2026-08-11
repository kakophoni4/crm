"""Catalog of sub-service types for deals with service «Деревья»."""

from __future__ import annotations

TREE_SERVICE_TYPE_OPTIONS: list[tuple[str, str]] = [
    ("archive_extract", "Архивная выписка"),
    ("book", "Книга"),
    ("tree", "Дерево"),
    ("base", "База"),
    ("sur", "СУР"),
    ("other", "Другое"),
    ("deposit", "Депозит"),
]

TREE_SERVICE_TYPE_CODES: frozenset[str] = frozenset(code for code, _ in TREE_SERVICE_TYPE_OPTIONS)
TREE_SERVICE_TYPE_LABELS: dict[str, str] = {code: label for code, label in TREE_SERVICE_TYPE_OPTIONS}


def normalize_tree_type_code(value: str | None) -> str | None:
    if value is None:
        return None
    code = value.strip().lower()
    if code not in TREE_SERVICE_TYPE_CODES:
        return None
    return code
