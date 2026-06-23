from __future__ import annotations

from datetime import datetime

from app.modules.db.models.enums import MessageDirection


def chat_list_needs_reply(
    *,
    escalated_at: datetime | None,
    last_direction: MessageDirection | str | None,
) -> bool:
    """True when the chat still needs operator attention in the inbox list."""
    if escalated_at is not None:
        return True
    if last_direction is None:
        return False
    if isinstance(last_direction, MessageDirection):
        return last_direction == MessageDirection.INBOUND
    return str(last_direction).lower() == MessageDirection.INBOUND.value
