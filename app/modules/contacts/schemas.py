from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.db.models.enums import AuditAction, ContactStatus
from app.shared.validators.jsonb_limits import validate_custom_fields_map


class ContactCreateRequest(BaseModel):
    full_name: str = Field(min_length=1)
    phone: str | None = None
    email: str | None = None
    telegram_user_id: int | None = None
    telegram_username: str | None = None
    status: ContactStatus | None = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)

    @field_validator("custom_fields")
    @classmethod
    def _validate_custom_fields_create(cls, value: dict[str, Any]) -> dict[str, Any]:
        return validate_custom_fields_map(value) or {}
    assigned_department_id: int | None = None
    source: str | None = None
    open_workspace: bool = False
    workspace_group_id: int | None = None


class ContactUpdateRequest(BaseModel):
    full_name: str | None = None
    note: str | None = None
    phone: str | None = None
    email: str | None = None
    telegram_user_id: int | None = None
    telegram_username: str | None = None
    status: ContactStatus | None = None
    custom_fields: dict[str, Any] | None = None
    assigned_department_id: int | None = None
    source: str | None = None

    @field_validator("custom_fields")
    @classmethod
    def _validate_custom_fields_update(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        return validate_custom_fields_map(value)


class ContactWorkspaceResponse(BaseModel):
    chat_id: int
    lead_id: int
    group_id: int
    created_chat: bool
    created_lead: bool


class ContactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    note: str | None = None
    phone: str | None
    email: str | None
    telegram_username: str | None
    status: ContactStatus
    custom_fields: dict[str, Any]
    assigned_department_id: int | None
    source: str | None
    archived_at: datetime | None
    created_by: int
    created_at: datetime
    updated_at: datetime


class ContactAdminResponse(ContactResponse):
    telegram_user_id: int | None


class ContactListResponse(BaseModel):
    items: list[dict[str, Any]]
    next_cursor: str | None = None
    has_more: bool = False
    total: int | None = None


class FieldChangeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    contact_id: int
    field_name: str
    old_value: Any | None
    new_value: Any | None
    changed_by: int
    changed_at: datetime
    changer_full_name: str | None = None


class FieldHistoryResponse(BaseModel):
    items: list[FieldChangeResponse]


class ContactActivityItemResponse(BaseModel):
    id: str
    label: str
    occurred_at: datetime
    actor_name: str | None = None


class ContactActivityResponse(BaseModel):
    items: list[ContactActivityItemResponse]


class AuditEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    actor_id: int | None
    action: AuditAction
    entity_type: str
    entity_id: int
    payload: dict[str, Any]
    request_id: str | None
    created_at: datetime


class ContactAuditResponse(BaseModel):
    items: list[AuditEntryResponse]
