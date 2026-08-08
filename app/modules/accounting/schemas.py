from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, field_validator


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
    commission_rate_percent: Decimal | None = None
    volume_limit: Decimal | None = None
    is_active: bool
    period_codes: list[str] = Field(default_factory=list)


class AccountingUnitListResponse(BaseModel):
    items: list[AccountingUnitResponse]
    is_chief: bool


class AccountingUnitCategoryOption(BaseModel):
    code: str
    label: str
    base_rate_percent: Decimal | None = None


class AccountingUnitCategoriesResponse(BaseModel):
    items: list[AccountingUnitCategoryOption]


class AccountingUnitCreateRequest(BaseModel):
    inn: str = Field(min_length=10, max_length=12)
    kpp: str | None = None
    name: str = Field(min_length=1, max_length=512)
    category_code: str = Field(min_length=1, max_length=16)
    commission_rate_percent: Decimal = Field(ge=0, le=100)
    volume_limit: Decimal | None = Field(default=None, ge=0)
    period_codes: list[str] = Field(min_length=1)

    @field_validator("inn")
    @classmethod
    def _validate_inn(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned.isdigit() or len(cleaned) not in (10, 12):
            raise ValueError("ИНН должен содержать 10 или 12 цифр")
        return cleaned

    @field_validator("kpp")
    @classmethod
    def _validate_kpp(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            return None
        if not cleaned.isdigit() or len(cleaned) != 9:
            raise ValueError("КПП должен содержать 9 цифр")
        return cleaned

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Укажите название")
        return cleaned


class AccountingUnitPatchRequest(BaseModel):
    commission_rate_percent: Decimal | None = Field(default=None, ge=0, le=100)
    volume_limit: Decimal | None = Field(default=None, ge=0)
    clear_volume_limit: bool | None = None
    name: str | None = Field(default=None, min_length=1, max_length=512)
    category_code: str | None = Field(default=None, min_length=1, max_length=16)
    period_codes: list[str] | None = None
    is_active: bool | None = None

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Укажите название")
        return cleaned


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
    period_code: str | None = None
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
    orders_count: int = 0
    orders_volume_sum: Decimal = Decimal("0")


class AccountingUnitOrdersResponse(BaseModel):
    items: list[AccountingUnitOrderGroup]
    total: int
    limit: int
    offset: int


class AccountingOrderPeriodUpdateRequest(BaseModel):
    period_code: str = Field(min_length=1, max_length=16)


class AccountingOrderPeriodUpdateResponse(BaseModel):
    order_id: int
    period_code: str


class AccountingOrderLineItem(BaseModel):
    line_id: int
    line_no: int
    order_id: int
    lead_id: int
    order_no: int
    crm_id: str
    status: str
    payment_status: str
    period_code: str | None = None
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
    response_due_date: date | None = None
    receipt_due_date: date | None = None
    reply_status: str = "none"
    reply_error: str | None = None
    replied_at: datetime | None = None
    sbis_requirement_id: int | None = None
    has_pdf: bool
    pdf_filename: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    received_at: datetime
    created_at: datetime
    is_overdue: bool = False
    due_soon: bool = False


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
    response_due_date: date | None = None
    receipt_due_date: date | None = None
    reply_status: str = "none"
    reply_error: str | None = None
    replied_at: datetime | None = None
    sbis_requirement_id: int | None = None
    received_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    pdf_base64: str | None = Field(
        default=None,
        description="Base64-encoded PDF body (optional if multipart file is sent)",
    )
    pdf_filename: str | None = "requirement.pdf"


class AccountingRequirementReplyResponse(BaseModel):
    id: int
    reply_status: str
    reply_error: str | None = None
    replied_at: datetime | None = None
    dry_run: bool = False
    success: bool = False


class AccountingRequirementDueSummary(BaseModel):
    overdue: int = 0
    due_soon: int = 0
    unanswered: int = 0


class AccountingRequirementTaskCreateRequest(BaseModel):
    unit_inn: str | None = Field(default=None, max_length=12)
    assignee_id: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=512)
    description: str | None = None
    due_at: datetime | None = None
    file_ids: list[int] = Field(default_factory=list)
    task_type: str = "normal"


class AccountingTaskAssigneeOption(BaseModel):
    id: int
    full_name: str
    role: str


class AccountingTaskAssigneeListResponse(BaseModel):
    items: list[AccountingTaskAssigneeOption]


class AccountingRequirementIngestResponse(BaseModel):
    id: int
    external_id: str
    created: bool


class AccountingRequirementWebhookPayload(BaseModel):
    """Push payload from sbis-norm (meta only, no file)."""

    id: int
    inn: str | None = None
    document_date: str | None = None
    sbis_doc_id: str | None = None
    sbis_stage_id: str | None = None
    doc_title: str | None = None
    content_sha256: str | None = None
    storage_file_name: str | None = None
    created_at: str | None = None
    file_url_hint: str | None = None


class AccountingRequirementSyncResponse(BaseModel):
    fetched: int
    created: int
    existing: int
    failed: int
    marked_synced: int
    skipped_non_pdf: int = 0
    queued: bool = False
    mode: str | None = None
    errors: list[str] = Field(default_factory=list)


class AccountingRequirementPullClaimResponse(BaseModel):
    claimed: bool


class AccountingRequirementStatusUpdateRequest(BaseModel):
    status: str = Field(min_length=1, max_length=32)

    @field_validator("status")
    @classmethod
    def _validate_status(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if cleaned not in {"new", "answered"}:
            raise ValueError("status должен быть new или answered")
        return cleaned


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
    commission_rate_percent: Decimal | None = None
    volume_limit: Decimal | None = None
    is_active: bool = True
    period_codes: list[str] = Field(default_factory=list)
    accountant_user_id: int | None = None
    accountant_full_name: str | None = None


class AccountingUnitOwnerListResponse(BaseModel):
    items: list[AccountingUnitOwnerRow]
    accountants: list[AccountingAccountantOption]


class AccountingUnitOwnerUpdateRequest(BaseModel):
    accountant_user_id: int | None = None


class AccountingReceiptIngestResponse(BaseModel):
    id: int
    external_id: str
    supplier_inn: str
    period_code: str
    doc_kind: str
    is_correction: bool = False
    created: bool


class AccountingReceiptPullClaimResponse(BaseModel):
    claimed: bool


class AccountingReceiptSyncResponse(BaseModel):
    queued: bool = True
    mode: str = "agent"


class AccountingSalesBookIngestResponse(BaseModel):
    id: int
    external_id: str
    seller_inn: str
    buyer_inn: str
    created: bool
