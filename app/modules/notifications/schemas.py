from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class TelegramLinkOut(BaseModel):
    id: int
    telegram_user_id: int
    telegram_username: str | None = None
    created_at: datetime


class TelegramLinkCreateRequest(BaseModel):
    telegram_user_id: int = Field(gt=0)


class NotificationSettingsOut(BaseModel):
    group_senior_timeout_minutes: int
    mute_phrases: list[str]
    telegram_links: list[TelegramLinkOut]
    bot_username: str | None = None
    bot_enabled: bool
    can_link_multiple: bool
    can_view_history: bool
    can_manage_bot: bool


class NotificationSettingsPatchRequest(BaseModel):
    group_senior_timeout_minutes: int | None = Field(default=None, ge=1, le=1440)
    mute_phrases: list[str] | None = None


class NotificationBotAdminOut(BaseModel):
    is_enabled: bool
    bot_username: str | None = None
    has_token: bool
    updated_at: datetime | None = None
    webhook_hint: str


class NotificationBotAdminPatchRequest(BaseModel):
    bot_token: str | None = Field(default=None, min_length=10, max_length=200)
    is_enabled: bool | None = None


class StaffNotificationEventOut(BaseModel):
    id: int
    kind: str
    status: str
    contact_id: int | None
    chat_id: int | None
    group_id: int | None
    department_id: int | None
    target_user_id: int | None
    target_user_name: str | None = None
    telegram_user_id: int | None
    contact_name: str | None
    body_text: str | None
    created_at: datetime
    acked_at: datetime | None
    cancelled_at: datetime | None


class StaffNotificationHistoryResponse(BaseModel):
    items: list[StaffNotificationEventOut]
    next_cursor: int | None = None
