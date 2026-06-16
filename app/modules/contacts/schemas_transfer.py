from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.modules.db.models.enums import ChatStatus


class ContactTransferRequestBody(BaseModel):
    to_user_id: int
    comment: str | None = None
    force: bool = False


class ContactTransferResponse(BaseModel):
    id: int
    contact_id: int
    contact_name: str | None = None
    group_id: int
    group_name: str | None = None
    from_user_id: int
    from_user_name: str | None = None
    to_user_id: int
    to_user_name: str | None = None
    requested_by: int
    requested_by_name: str | None = None
    state: str
    senior_user_id: int | None = None
    senior_decided_at: datetime | None = None
    recipient_decided_at: datetime | None = None
    force_assigned: bool = False
    comment: str | None = None
    expires_at: datetime
    version: int = 1
    created_at: datetime
    updated_at: datetime


class ContactTransferListResponse(BaseModel):
    items: list[ContactTransferResponse]


class GroupOwnershipItem(BaseModel):
    group_id: int
    group_name: str
    owner_user_id: int | None
    owner_full_name: str | None
    pending_inbound_at: datetime | None
    escalated_at: datetime | None


class ContactBotLink(BaseModel):
    bot_id: int
    bot_code: str
    bot_name: str
    chat_id: int
    chat_status: ChatStatus


class ReplyAuditItem(BaseModel):
    message_id: int
    chat_id: int
    author_user_id: int
    author_full_name: str
    card_owner_user_id: int
    card_owner_full_name: str
    is_on_behalf: bool
    created_at: datetime


class ReplyAuditListResponse(BaseModel):
    items: list[ReplyAuditItem]


class EscalationSettingsResponse(BaseModel):
    group_id: int
    first_response_timeout_minutes: int
    new_contact_reassign_strategy: str
    notify_owner_on_inbound: bool
    notify_group_on_escalation: bool
    updated_at: datetime


class EscalationSettingsPatchRequest(BaseModel):
    first_response_timeout_minutes: int | None = Field(default=None, ge=1, le=1440)
    new_contact_reassign_strategy: str | None = None
    notify_owner_on_inbound: bool | None = None
    notify_group_on_escalation: bool | None = None
