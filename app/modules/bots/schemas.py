from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.modules.db.models.enums import BotOwnerType


class BotCreateRequest(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=256)
    department_id: int | None = Field(default=None, gt=0)
    owner_type: BotOwnerType | None = None
    owner_id: int | None = Field(default=None, gt=0)
    outbound_url: str
    health_url: str | None = None
    ip_allowlist: list[str] | None = None
    inbound_secret: str = Field(min_length=16)
    outbound_secret: str = Field(min_length=16)

    @model_validator(mode="after")
    def _require_department(self) -> BotCreateRequest:
        if self.department_id is not None:
            return self
        if self.owner_type is None or self.owner_id is None:
            raise ValueError("department_id is required")
        return self


class BotUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=256)
    department_id: int | None = Field(default=None, gt=0)
    owner_type: BotOwnerType | None = None
    owner_id: int | None = Field(default=None, gt=0)
    outbound_url: str | None = None
    health_url: str | None = None
    ip_allowlist: list[str] | None = None
    is_active: bool | None = None


class BotGroupAssignmentsRequest(BaseModel):
    group_ids: list[int] = Field(default_factory=list)


class BotSecretsResponse(BaseModel):
    inbound_secret: str | None = None
    outbound_secret: str | None = None
    warning: str = (
        "Это единственный раз, когда секреты видны. Сохраните их в хранилище бота."
    )


class BotResponse(BaseModel):
    id: int
    code: str
    name: str
    department_id: int
    department_name: str | None = None
    assigned_group_ids: list[int] = Field(default_factory=list)
    assigned_group_names: list[str] = Field(default_factory=list)
    owner_label: str = ""
    owner_type: BotOwnerType
    owner_id: int
    outbound_url: str
    health_url: str | None
    ip_allowlist: list[str] | None
    is_active: bool
    last_seen_at: str | None
    last_health_status: str | None
    last_health_checked_at: str | None
    created_at: str
    updated_at: str


class BotCreateResponse(BotResponse):
    secrets: BotSecretsResponse | None = None


class BotListResponse(BaseModel):
    items: list[BotResponse]


class RotateSecretRequest(BaseModel):
    kind: Literal["inbound", "outbound"]


class RotateSecretResponse(BaseModel):
    kind: Literal["inbound", "outbound"]
    secret: str


class BotHealthResponse(BaseModel):
    bot_id: int
    status: str
    checked_at: str
    http_status: int | None = None


class BotEventAcceptedResponse(BaseModel):
    status: Literal["accepted", "duplicate"] = "accepted"
