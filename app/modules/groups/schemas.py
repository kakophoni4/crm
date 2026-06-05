from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class GroupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    department_id: int
    created_at: datetime
    updated_at: datetime


class GroupListResponse(BaseModel):
    items: list[GroupOut]


class GroupCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=256)
    department_id: int = Field(gt=0)


class GroupUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=256)
