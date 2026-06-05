from __future__ import annotations

from enum import StrEnum
from typing import Any

from sqlalchemy import nulls_last

from app.modules.db.models.chat import Chat


class ChatListSort(StrEnum):
    LAST_MESSAGE_AT_DESC = "last_message_at_desc"
    CREATED_AT_DESC = "created_at_desc"
    UNREAD_FIRST = "unread_first"


def chat_list_order_by(sort: ChatListSort) -> list[Any]:
    if sort == ChatListSort.CREATED_AT_DESC:
        return [Chat.created_at.desc(), Chat.id.desc()]
    if sort == ChatListSort.UNREAD_FIRST:
        # Per-operator sort is applied in ChatRepository when actor_user_id is set.
        return [nulls_last(Chat.last_message_at.desc()), Chat.id.desc()]
    return [nulls_last(Chat.last_message_at.desc()), Chat.id.desc()]
