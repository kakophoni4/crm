from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from app.modules.chats.schemas import ChatListItemResponse, ChatMessageSearchItem
from app.modules.contacts.schemas import ContactResponse


class SearchType(StrEnum):
    CONTACTS = "contacts"
    MESSAGES = "messages"
    CHATS = "chats"


class SearchResultSection[T](BaseModel):
    items: list[T] = Field(default_factory=list)
    next_cursor: str | None = None


class GlobalSearchResponse(BaseModel):
    contacts: SearchResultSection[ContactResponse]
    messages: SearchResultSection[ChatMessageSearchItem]
    chats: SearchResultSection[ChatListItemResponse]
