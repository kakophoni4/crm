from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.modules.db.models.enums import ChatStatus, MessageKind


class AttachmentInput(BaseModel):
    file_id: int | None = None
    name: str | None = None
    mime: str | None = None
    size: int | None = None
    url: str | None = None


class ChatCreateRequest(BaseModel):
    contact_id: int
    bot_id: int | None = None
    assigned_user_id: int | None = None
    assigned_group_id: int | None = None
    assigned_department_id: int | None = None
    status_id: int | None = None


class WhatsappOutreachRequest(BaseModel):
    """Start (or reopen) a WhatsApp chat by phone — for first outbound message from CRM."""

    phone: str = Field(min_length=8, max_length=32)
    full_name: str = Field(min_length=1, max_length=256)
    bot_id: int = Field(gt=0)


class WhatsappOutreachResponse(BaseModel):
    chat_id: int
    contact_id: int
    created_chat: bool


class ChatReferralResponse(BaseModel):
    enabled: bool
    url: str | None = None
    code: str | None = None
    count: int = 0


class ChatStatusPatchRequest(BaseModel):
    status: Literal["open", "in_progress", "closed", "archived"]


class ChatStatusIdPatchRequest(BaseModel):
    status_id: int


class OutboundMessageRequest(BaseModel):
    text: str | None = None
    kind: MessageKind = MessageKind.TEXT
    attachments: list[AttachmentInput] = Field(default_factory=list)
    idempotency_key: str | None = None
    reply_to_message_id: int | None = None


class TakeoverRequestBody(BaseModel):
    reason: str | None = None


class QuickReplyTemplateCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    body: str = Field(min_length=1, max_length=4000)
    department_id: int | None = Field(default=None, gt=0)
    group_id: int | None = Field(default=None, gt=0)
    """shared = group/department template; personal = only for current user."""
    scope: Literal["shared", "personal"] = "shared"
    is_active: bool = True


class QuickReplyTemplateUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    body: str | None = Field(default=None, min_length=1, max_length=4000)
    department_id: int | None = Field(default=None, gt=0)
    group_id: int | None = Field(default=None, gt=0)
    is_active: bool | None = None


class QuickReplyTemplateResponse(BaseModel):
    id: int
    title: str
    body: str
    department_id: int | None
    group_id: int | None
    owner_user_id: int | None = None
    scope: Literal["shared", "personal"] = "shared"
    is_active: bool
    usage_count: int
    created_at: datetime
    updated_at: datetime


class QuickReplyTemplateListResponse(BaseModel):
    items: list[QuickReplyTemplateResponse]


class ChatMarkReadRequest(BaseModel):
    last_read_message_id: int | None = None


class ChatMarkReadResponse(BaseModel):
    chat_id: int
    user_id: int
    last_read_message_id: int | None
    read_at: str


class CurrentLeadSnippet(BaseModel):
    id: int
    status_id: int
    label: str
    comment: str | None = None
    closed_at: datetime | None


class ChatLabelSnippet(BaseModel):
    status_id: int | None
    code: str | None
    label: str | None


class ChatListItemResponse(BaseModel):
    id: int
    contact_id: int
    contact_name: str
    bot_id: int | None
    bot_name: str | None = None
    assigned_user_id: int | None = Field(
        default=None,
        description=(
            "Deprecated: last handled operator (DB last_handled_by_user_id), not card owner."
        ),
    )
    assigned_group_id: int | None
    assigned_group_name: str | None = None
    assigned_department_id: int | None
    card_owner_user_id: int | None = None
    card_owner_name: str | None = None
    card_owner_full_name: str | None = None
    card_owner_group_id: int | None = None
    status: ChatStatus
    status_id: int | None
    chat_label: ChatLabelSnippet | None = None
    contact_client_label: str | None = None
    contact_illiquid: bool = False
    current_lead: CurrentLeadSnippet | None = None
    last_message_at: datetime | None
    last_message_preview: str | None
    unread_for_me: bool = False
    pending_inbound_at: datetime | None = None
    escalated_at: datetime | None = None
    needs_reply: bool = False


class ChatListResponse(BaseModel):
    items: list[ChatListItemResponse]
    next_cursor: str | None


class ChatMessageSearchItem(BaseModel):
    chat_id: int
    contact_id: int
    message_id: int
    snippet: str
    matched_at: datetime
    lead_id: int | None = None
    card_owner_user_id: int | None = None


class ChatMessageSearchResponse(BaseModel):
    items: list[ChatMessageSearchItem]
    next_cursor: str | None


class MessageResponse(BaseModel):
    id: int
    chat_id: int
    lead_id: int | None = None
    direction: str
    kind: str
    text: str | None
    attachments: list[dict[str, Any]]
    sender_user_id: int | None
    sender_username: str | None = None
    external_message_id: str | None = None
    external_event_id: str | None = None
    reply_to_message_id: int | None
    created_at: datetime
    idempotency_key: str | None = None
    card_owner_user_id: int | None = None
    card_owner_name: str | None = None
    card_owner_group_id: int | None = None


class MessageListResponse(BaseModel):
    items: list[MessageResponse]
    next_cursor: str | None


class TakeoverResponse(BaseModel):
    id: int
    chat_id: int
    senior_user_id: int
    started_at: datetime
    released_at: datetime | None
    reason: str | None
