from __future__ import annotations

import json
from typing import Any

from app.modules.db.models.contact import Contact

_TRACKED_FIELDS = (
    "full_name",
    "note",
    "phone",
    "email",
    "telegram_username",
    "telegram_user_id",
    "status",
    "assigned_department_id",
    "source",
)


def _json_value(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "value"):
        return value.value
    return value


def diff_snapshots(
    before: dict[str, Any],
    after: dict[str, Any],
) -> list[tuple[str, Any | None, Any | None]]:
    changes: list[tuple[str, Any | None, Any | None]] = []

    for field in _TRACKED_FIELDS:
        old_val = before.get(field)
        new_val = after.get(field)
        if old_val != new_val:
            changes.append((field, old_val, new_val))

    old_custom = before.get("custom_fields") or {}
    new_custom = after.get("custom_fields") or {}
    all_keys = set(old_custom) | set(new_custom)
    for key in sorted(all_keys):
        old_item = old_custom.get(key)
        new_item = new_custom.get(key)
        if old_item != new_item:
            changes.append((f"custom_fields.{key}", old_item, new_item))

    return changes


def diff_contact_fields(
    before: Contact,
    after: Contact,
) -> list[tuple[str, Any | None, Any | None]]:
    return diff_snapshots(snapshot_contact(before), snapshot_contact(after))


def snapshot_contact(contact: Contact) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for field in _TRACKED_FIELDS:
        data[field] = _json_value(getattr(contact, field))
    data["custom_fields"] = dict(contact.custom_fields or {})
    return data


def audit_diff_payload(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    return {"before": before, "after": after, "changed": _diff_dicts(before, after)}


def _diff_dicts(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    changed: dict[str, Any] = {}
    keys = set(before) | set(after)
    for key in keys:
        if before.get(key) != after.get(key):
            changed[key] = {"old": before.get(key), "new": after.get(key)}
    return changed


def to_jsonb(value: Any) -> Any:
    if value is None:
        return None
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return str(value)
