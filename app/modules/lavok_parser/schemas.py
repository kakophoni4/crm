from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class LavokParserLotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    inn: str
    sheet_date: date
    source: str | None = None
    name: str | None = None
    price: str | None = None
    registered_at: str | None = None
    tax: str | None = None
    address_director: str | None = None
    courts: str | None = None
    debts: str | None = None
    egrul_reliability: str | None = None
    bankruptcy: str | None = None
    turnover: str | None = None
    reporting: str | None = None
    leasing: str | None = None
    zsk: str | None = None
    summary: str | None = None
    score: str | None = None
    first_seen: str | None = None
    seller: str | None = None
    link: str | None = None
    companium: str | None = None
    egrul_status: str | None = None
    mark: str
    note: str | None = None
    is_deleted: bool
    created_at: datetime
    updated_at: datetime


class LavokParserListResponse(BaseModel):
    items: list[LavokParserLotOut]
    total: int
    sheet_dates: list[date]
    sheet_date: date | None = None


class LavokParserIngestResponse(BaseModel):
    sheets: int
    upserted: int
    created: int
    updated: int


class LavokParserIngestJsonItem(BaseModel):
    inn: str
    sheet_date: str
    source: str | None = None
    name: str | None = None
    price: str | None = None
    registered_at: str | None = None
    tax: str | None = None
    address_director: str | None = None
    courts: str | None = None
    debts: str | None = None
    egrul_reliability: str | None = None
    bankruptcy: str | None = None
    turnover: str | None = None
    reporting: str | None = None
    leasing: str | None = None
    zsk: str | None = None
    summary: str | None = None
    score: str | None = None
    first_seen: str | None = None
    seller: str | None = None
    link: str | None = None
    companium: str | None = None
    egrul_status: str | None = None


class LavokParserIngestJsonRequest(BaseModel):
    items: list[LavokParserIngestJsonItem] = Field(min_length=1, max_length=80)


class LavokParserLotPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mark: str | None = Field(default=None, max_length=32)
    note: str | None = Field(default=None, max_length=4000)
