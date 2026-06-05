from __future__ import annotations

import base64
import json
from datetime import datetime
from typing import Any


class CursorError(ValueError):
    pass


def _iso(dt: datetime) -> str:
    return dt.replace(tzinfo=None).isoformat()


def encode_message_cursor(created_at: datetime, message_id: int) -> str:
    payload = json.dumps(
        {"at": _iso(created_at), "id": message_id},
        separators=(",", ":"),
    )
    return base64.urlsafe_b64encode(payload.encode()).decode()


def decode_message_cursor(cursor: str) -> tuple[datetime, int]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode())
        data: dict[str, Any] = json.loads(raw)
        created_at = datetime.fromisoformat(str(data["at"])).replace(tzinfo=None)
        message_id = int(data["id"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise CursorError("Invalid cursor") from exc
    if message_id < 1:
        raise CursorError("Invalid cursor")
    return created_at, message_id


def encode_chat_cursor(last_message_at: datetime, chat_id: int) -> str:
    payload = json.dumps(
        {"at": _iso(last_message_at), "id": chat_id},
        separators=(",", ":"),
    )
    return base64.urlsafe_b64encode(payload.encode()).decode()


def decode_chat_cursor(cursor: str) -> tuple[datetime, int]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode())
        data: dict[str, Any] = json.loads(raw)
        last_message_at = datetime.fromisoformat(str(data["at"])).replace(tzinfo=None)
        chat_id = int(data["id"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise CursorError("Invalid cursor") from exc
    if chat_id < 1:
        raise CursorError("Invalid cursor")
    return last_message_at, chat_id
