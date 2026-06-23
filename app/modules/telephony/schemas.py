from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class TelephonyAccountCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=256)
    provider: str = Field(default="bitcall", min_length=1, max_length=64)
    department_id: int = Field(gt=0)
    group_id: int | None = Field(default=None, gt=0)
    group_ids: list[int] = Field(default_factory=list)
    sip_host: str = Field(min_length=1, max_length=256)
    sip_port: int = Field(default=5060, ge=1, le=65535)
    sip_transport: str = Field(default="udp", pattern="^(udp|tcp|tls)$")
    sip_username: str = Field(min_length=1, max_length=256)
    sip_password: str = Field(min_length=1, max_length=1024)
    outbound_caller_id: str | None = Field(default=None, max_length=64)
    pbx_extension_prefix: str | None = Field(default=None, max_length=32)
    webrtc_ws_url: str | None = Field(default=None, max_length=512)


class TelephonyAccountUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=256)
    group_id: int | None = Field(default=None, gt=0)
    group_ids: list[int] | None = None
    sip_host: str | None = Field(default=None, min_length=1, max_length=256)
    sip_port: int | None = Field(default=None, ge=1, le=65535)
    sip_transport: str | None = Field(default=None, pattern="^(udp|tcp|tls)$")
    sip_username: str | None = Field(default=None, min_length=1, max_length=256)
    sip_password: str | None = Field(default=None, min_length=1, max_length=1024)
    outbound_caller_id: str | None = Field(default=None, max_length=64)
    pbx_extension_prefix: str | None = Field(default=None, max_length=32)
    webrtc_ws_url: str | None = Field(default=None, max_length=512)
    is_active: bool | None = None


class TelephonyAccountResponse(BaseModel):
    id: int
    name: str
    provider: str
    department_id: int
    department_name: str | None = None
    group_id: int | None
    group_name: str | None = None
    group_ids: list[int] = Field(default_factory=list)
    group_names: list[str] = Field(default_factory=list)
    sip_host: str
    sip_port: int
    sip_transport: str
    sip_username: str
    has_sip_password: bool
    outbound_caller_id: str | None
    pbx_extension_prefix: str | None
    webrtc_ws_url: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class TelephonyAccountListResponse(BaseModel):
    items: list[TelephonyAccountResponse]


class TelephonyWebrtcConfigResponse(BaseModel):
    account_id: int
    account_name: str
    extension: str
    extension_password: str
    extension_created: bool = False
    display_name: str | None
    sip_uri: str
    ws_url: str
    outbound_caller_id: str | None
    ice_servers: list[dict[str, object]] = Field(default_factory=list)
