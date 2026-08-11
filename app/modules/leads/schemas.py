from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.shared.validators.jsonb_limits import (
    MAX_LEAD_COMMENT_LEN,
    validate_custom_fields_map,
)


class LeadCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    group_id: int
    bot_id: int | None = None
    status_id: int | None = None


class LeadPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status_id: int | None = None
    comment: str | None = Field(default=None, max_length=MAX_LEAD_COMMENT_LEN)
    custom_fields: dict[str, Any] | None = None

    @field_validator("custom_fields")
    @classmethod
    def _validate_custom_fields(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        return validate_custom_fields_map(value)


class LeadCommentItemResponse(BaseModel):
    id: int
    body: str
    created_at: datetime


class LeadListItemResponse(BaseModel):
    id: int
    contact_id: int
    group_id: int
    bot_id: int | None
    chat_id: int | None
    status_id: int | None = None
    status_code: str | None = None
    status_label: str | None = None
    bot_name: str | None = None
    bot_code: str | None = None
    title: str | None = None
    comment: str | None = None
    comments: list[LeadCommentItemResponse] = Field(default_factory=list)
    closed_at: datetime | None
    created_at: datetime
    custom_fields: dict[str, Any] | None = None


class LeadDetailResponse(LeadListItemResponse):
    updated_at: datetime


class LeadListResponse(BaseModel):
    items: list[LeadListItemResponse]
    next_cursor: str | None


class ContactCrmSummaryResponse(BaseModel):
    prior_leads_count: int
    first_registered_at: datetime


class PipelineStatusCount(BaseModel):
    status_id: int
    code: str
    label: str
    count: int


class OperatorDashboardKpi(BaseModel):
    user_id: int
    display_name: str
    chats_today_count: int
    avg_response_minutes: float | None
    closed_won_today_count: int
    closed_lost_today_count: int
    open_leads_count: int


class CrmDashboardSummaryResponse(BaseModel):
    chats_today_count: int
    avg_response_minutes: float | None
    closed_leads_today_count: int
    closed_won_today_count: int
    closed_lost_today_count: int
    new_clients_today_count: int
    open_leads_count: int
    closed_today_count: int
    by_pipeline_status: list[PipelineStatusCount]
    by_operator: list[OperatorDashboardKpi] = Field(default_factory=list)


class LeadCloseRequest(BaseModel):
    status_id: int


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


class LeadRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    contact_id: int
    group_id: int
    bot_id: int | None
    chat_id: int | None
    status_id: int
    closed_at: datetime | None


class TreeServiceTypeOption(BaseModel):
    type_code: str
    label: str
    unit_price: float | None = None
    is_active: bool = True


class TreeServiceTypeListResponse(BaseModel):
    items: list[TreeServiceTypeOption]


class TreeServicePricePatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    unit_price: float | None = Field(default=None, ge=0)
    is_active: bool | None = None
