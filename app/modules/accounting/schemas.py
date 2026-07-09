from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class AccountingSupplierResponse(BaseModel):
    inn: str
    kpp: str | None = None
    name: str | None = None
    category_code: str | None = None


class AccountingUnitResponse(BaseModel):
    id: int
    inn: str
    kpp: str | None = None
    name: str | None = None
    category_code: str | None = None
    is_active: bool


class AccountingUnitListResponse(BaseModel):
    items: list[AccountingUnitResponse]
    is_chief: bool


class AccountingOrderLineBrief(BaseModel):
    line_id: int
    line_no: int
    document_date: date
    amount: Decimal
    document_number: str | None = None


class AccountingUnitOrderItem(BaseModel):
    order_id: int
    lead_id: int
    order_no: int
    crm_id: str
    status: str
    payment_status: str
    amount_paid: Decimal
    commission_due: Decimal
    lavka_line_volume: Decimal
    line_count: int
    lines: list[AccountingOrderLineBrief] = Field(default_factory=list)
    buyer_inn: str
    buyer_name: str | None = None
    source_filename: str | None = None
    manager_user_id: int | None = None
    manager_full_name: str | None = None
    contact_name: str | None = None
    submitted_at: datetime | None = None
    created_at: datetime
    submission_error: str | None = None


class AccountingUnitOrderGroup(BaseModel):
    unit: AccountingUnitResponse
    orders: list[AccountingUnitOrderItem] = Field(default_factory=list)


class AccountingUnitOrdersResponse(BaseModel):
    items: list[AccountingUnitOrderGroup]
    total: int
    limit: int
    offset: int


class AccountingOrderLineItem(BaseModel):
    line_id: int
    line_no: int
    order_id: int
    lead_id: int
    order_no: int
    crm_id: str
    status: str
    payment_status: str
    supplier: AccountingSupplierResponse
    buyer_inn: str
    buyer_name: str | None = None
    document_date: date
    amount: Decimal
    manager_user_id: int | None = None
    manager_full_name: str | None = None
    contact_name: str | None = None
    source_filename: str | None = None
    submitted_at: datetime | None = None
    created_at: datetime


class AccountingOrderLineListResponse(BaseModel):
    items: list[AccountingOrderLineItem]
    total: int
    limit: int
    offset: int


class AccountingRequirementResponse(BaseModel):
    id: int
    external_id: str
    supplier: AccountingSupplierResponse
    title: str
    description: str | None = None
    status: str
    has_pdf: bool
    pdf_filename: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    received_at: datetime
    created_at: datetime


class AccountingRequirementListResponse(BaseModel):
    items: list[AccountingRequirementResponse]
    total: int
    limit: int
    offset: int


class AccountingRequirementIngestRequest(BaseModel):
    """JSON ingest format for external requirement service.

    Multipart alternative: fields external_id, supplier_inn, title, ... + file pdf.
    """

    external_id: str = Field(min_length=1, max_length=256)
    supplier_inn: str = Field(min_length=10, max_length=12)
    supplier_kpp: str | None = None
    supplier_name: str | None = None
    title: str = Field(min_length=1, max_length=512)
    description: str | None = None
    status: str = "new"
    received_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    pdf_base64: str | None = Field(
        default=None,
        description="Base64-encoded PDF body (optional if multipart file is sent)",
    )
    pdf_filename: str | None = "requirement.pdf"


class AccountingRequirementIngestResponse(BaseModel):
    id: int
    external_id: str
    created: bool


class AccountingAssignmentItem(BaseModel):
    user_id: int
    user_full_name: str
    unit_ids: list[int]


class AccountingAssignmentListResponse(BaseModel):
    items: list[AccountingAssignmentItem]


class AccountingAssignmentUpdateRequest(BaseModel):
    unit_ids: list[int] = Field(default_factory=list)


class AccountingAccountantOption(BaseModel):
    user_id: int
    full_name: str


class AccountingUnitOwnerRow(BaseModel):
    unit_id: int
    inn: str
    name: str | None = None
    category_code: str | None = None
    accountant_user_id: int | None = None
    accountant_full_name: str | None = None


class AccountingUnitOwnerListResponse(BaseModel):
    items: list[AccountingUnitOwnerRow]
    accountants: list[AccountingAccountantOption]


class AccountingUnitOwnerUpdateRequest(BaseModel):
    accountant_user_id: int | None = None
