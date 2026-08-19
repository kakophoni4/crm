from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class TicketsInnsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inns: list[str] = Field(min_length=1, max_length=500)
    check_new: bool = True


class TicketCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_id: int
    issue_type: str = Field(min_length=1, max_length=32)
    title: str = Field(min_length=1, max_length=512)
    details: str | None = Field(default=None, max_length=4000)


class CompanyPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inn: str | None = Field(default=None, max_length=12)
    is_active: bool | None = None
    name: str | None = Field(default=None, max_length=512)
