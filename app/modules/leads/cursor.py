from __future__ import annotations

import base64
import json
from datetime import datetime
from typing import Any


class CursorError(ValueError):
    pass


def encode_lead_cursor(created_at: datetime, lead_id: int) -> str:
    payload = json.dumps(
        {"created_at": created_at.isoformat(), "id": lead_id},
        separators=(",", ":"),
    )
    return base64.urlsafe_b64encode(payload.encode()).decode()


def decode_lead_cursor(cursor: str) -> tuple[datetime, int]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode())
        data: dict[str, Any] = json.loads(raw)
        created_at = datetime.fromisoformat(str(data["created_at"]))
        lead_id = int(data["id"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise CursorError("Invalid cursor") from exc
    if lead_id < 1:
        raise CursorError("Invalid cursor")
    return created_at, lead_id
