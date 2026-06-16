from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.modules.db.models.enums import BotChannel, BotOwnerType


class BotCreateRequest(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=256)
    channel: BotChannel = BotChannel.TELEGRAM
    department_id: int | None = Field(default=None, gt=0)
    owner_type: BotOwnerType | None = None
    owner_id: int | None = Field(default=None, gt=0)
    outbound_url: str | None = None
    health_url: str | None = None
    ip_allowlist: list[str] | None = None
    inbound_secret: str | None = Field(default=None, min_length=16)
    outbound_secret: str | None = Field(default=None, min_length=16)
    green_api_url: str | None = None
    green_media_url: str | None = None
    green_instance_id: str | None = None
    green_api_token: str | None = Field(default=None, min_length=8)

    @model_validator(mode="after")
    def _validate_channel(self) -> BotCreateRequest:
        if self.department_id is None and (self.owner_type is None or self.owner_id is None):
            raise ValueError("department_id is required")
        if self.channel == BotChannel.WHATSAPP:
            if not self.green_instance_id or not self.green_api_token:
                raise ValueError("green_instance_id and green_api_token are required for WhatsApp")
            return self
        if not self.outbound_url:
            raise ValueError("outbound_url is required for Telegram bots")
        if not self.inbound_secret or not self.outbound_secret:
            raise ValueError("inbound_secret and outbound_secret are required for Telegram bots")
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
    green_api_url: str | None = None
    green_media_url: str | None = None
    green_instance_id: str | None = None
    green_api_token: str | None = Field(default=None, min_length=8)


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
    channel: BotChannel = BotChannel.TELEGRAM
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
    green_api_url: str | None = None
    green_media_url: str | None = None
    green_instance_id: str | None = None
    has_green_api_token: bool = False
    whatsapp_webhook_url: str | None = None
    last_seen_at: str | None
    last_health_status: str | None
    last_health_checked_at: str | None
    created_at: str
    updated_at: str


class BotCreateResponse(BotResponse):
    secrets: BotSecretsResponse | None = None


class BotListResponse(BaseModel):
    items: list[BotResponse]


class WaBridgeBotConfig(BaseModel):
    bot_code: str
    inbound_secret: str
    outbound_secret: str
    green_api_url: str
    green_media_url: str
    green_instance_id: str
    green_api_token: str


class WaBridgeConfigResponse(BaseModel):
    items: list[WaBridgeBotConfig]


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
