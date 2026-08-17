from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class IdleBannerStatus(BaseModel):
    is_enabled: bool
    has_image: bool
    image_version: int


class IdleBannerPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_enabled: bool


class IdleBannerSendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_ids: list[int] = Field(min_length=1, max_length=500)


class IdleBannerSendResponse(BaseModel):
    sent: int
