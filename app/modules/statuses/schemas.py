from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


class StatusOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    kind: Literal["chat_label", "lead_pipeline"]
    label: str
    color: str | None
    sort_order: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class StatusListResponse(BaseModel):
    items: list[StatusOut]


class StatusCreateRequest(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    kind: Literal["chat_label", "lead_pipeline"] = "lead_pipeline"
    label: str = Field(min_length=1, max_length=256)
    color: str | None = None
    sort_order: int = 0

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized.replace("_", "").isalnum():
            msg = "code must contain only letters, digits, and underscores"
            raise ValueError(msg)
        return normalized

    @field_validator("color")
    @classmethod
    def validate_color(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not _HEX_COLOR_RE.match(value):
            msg = "color must be a hex value like #RRGGBB"
            raise ValueError(msg)
        return value.upper()


class StatusUpdateRequest(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=256)
    color: str | None = None
    sort_order: int | None = None

    @field_validator("color")
    @classmethod
    def validate_color(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not _HEX_COLOR_RE.match(value):
            msg = "color must be a hex value like #RRGGBB"
            raise ValueError(msg)
        return value.upper()
