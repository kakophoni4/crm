from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


def _money(value: Decimal | float | None) -> float | None:
    if value is None:
        return None
    return float(value)


class LawyerShopOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    inn: str
    name: str
    director_id: int | None = None
    director_name: str | None = None
    kind: str
    registered_at: date | None = None
    planned_payout: float | None = None
    company_status: str | None = None
    sale_priority: str | None = None
    unreliable: str | None = None
    treatment_status: str | None = None
    ecsp_status: str | None = None
    ecsp_until: date | None = None
    zsk: str | None = None
    banks: str | None = None
    accounts_status: str | None = None
    manager: str | None = None
    phone: str | None = None
    telegram: str | None = None
    accountant: str | None = None
    comment: str | None = None
    source: str
    last_parser_at: datetime | None = None
    pinned_at: datetime | None = None
    hidden_at: datetime | None = None
    created_at: datetime


class LawyerPaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    director_id: int
    shop_id: int | None = None
    shop_name: str | None = None
    period_ym: str
    amount: float
    paid_at: date | None = None
    note: str | None = None
    created_at: datetime


class LawyerDirectorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    salary_plan: float | None = None
    dirovod: str | None = None
    company_status: str | None = None
    companies_status: str | None = None
    ecsp_status: str | None = None
    ecsp_until: date | None = None
    banks: str | None = None
    accounts_status: str | None = None
    phone: str | None = None
    telegram: str | None = None
    passport: str | None = None
    inn_personal: str | None = None
    snils: str | None = None
    birth_date: date | None = None
    in_touch: str | None = None
    note: str | None = None
    pinned_at: datetime | None = None
    shop_count: int = 0
    last_paid_period: str | None = None
    shops: list[LawyerShopOut] = Field(default_factory=list)
    payments: list[LawyerPaymentOut] = Field(default_factory=list)


class LawyerDirectorListResponse(BaseModel):
    items: list[LawyerDirectorOut]
    orphan_shops: list[LawyerShopOut] = Field(default_factory=list)
    pinned_shops: list[LawyerShopOut] = Field(default_factory=list)
    total_directors: int
    total_shops: int
    unread_alerts: int


class LawyerShopCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inn: str = Field(min_length=8, max_length=12)
    name: str = Field(min_length=1, max_length=512)
    director_name: str | None = Field(default=None, max_length=255)
    director_id: int | None = None
    kind: str = Field(default="new", max_length=32)
    registered_at: date | None = None
    planned_payout: float | None = None
    company_status: str | None = None
    sale_priority: str | None = None
    unreliable: str | None = None
    treatment_status: str | None = None
    ecsp_status: str | None = None
    ecsp_until: date | None = None
    zsk: str | None = None
    banks: str | None = None
    accounts_status: str | None = None
    manager: str | None = None
    phone: str | None = None
    telegram: str | None = None
    accountant: str | None = None
    comment: str | None = None


class LawyerShopPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=512)
    director_name: str | None = Field(default=None, max_length=255)
    director_id: int | None = None
    kind: str | None = Field(default=None, max_length=32)
    registered_at: date | None = None
    planned_payout: float | None = None
    company_status: str | None = None
    sale_priority: str | None = None
    unreliable: str | None = None
    treatment_status: str | None = None
    ecsp_status: str | None = None
    ecsp_until: date | None = None
    zsk: str | None = None
    banks: str | None = None
    accounts_status: str | None = None
    manager: str | None = None
    phone: str | None = None
    telegram: str | None = None
    accountant: str | None = None
    comment: str | None = None
    pinned: bool | None = None
    hidden: bool | None = None


class LawyerDirectorCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str = Field(min_length=1, max_length=255)
    salary_plan: float | None = None
    dirovod: str | None = None
    company_status: str | None = None
    companies_status: str | None = None
    ecsp_status: str | None = None
    ecsp_until: date | None = None
    banks: str | None = None
    accounts_status: str | None = None
    phone: str | None = None
    telegram: str | None = None
    passport: str | None = None
    inn_personal: str | None = None
    snils: str | None = None
    birth_date: date | None = None
    in_touch: str | None = None
    note: str | None = None


class LawyerDirectorPatchRequest(LawyerDirectorCreateRequest):
    full_name: str | None = Field(default=None, max_length=255)
    pinned: bool | None = None


class LawyerPaymentCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shop_id: int | None = None
    period_ym: str = Field(min_length=7, max_length=7, pattern=r"^\d{4}-\d{2}$")
    amount: float = Field(gt=0)
    paid_at: date | None = None
    note: str | None = None


class LawyerAlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    shop_id: int | None = None
    inn: str
    title: str
    details: str | None = None
    is_read: bool
    created_at: datetime


class LawyerAlertListResponse(BaseModel):
    items: list[LawyerAlertOut]
    unread: int


class LawyerImportResponse(BaseModel):
    directors: int
    shops: int
    payments: int
    updated: int


class LawyerAlertReadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ids: list[int] | None = None
