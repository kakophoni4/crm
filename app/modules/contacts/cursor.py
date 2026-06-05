from __future__ import annotations

import base64
import json
from typing import Any


class CursorError(ValueError):
    pass


def encode_cursor(contact_id: int) -> str:
    payload = json.dumps({"id": contact_id}, separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode()).decode()


def decode_cursor(cursor: str) -> int:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode())
        data: dict[str, Any] = json.loads(raw)
        contact_id = int(data["id"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise CursorError("Invalid cursor") from exc
    if contact_id < 1:
        raise CursorError("Invalid cursor")
    return contact_id
