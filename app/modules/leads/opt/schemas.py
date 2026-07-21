from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class OptCounterpartyResponse(BaseModel):
    inn: str
    kpp: str | None = None
    name: str | None = None


class OptOrderLineResponse(BaseModel):
    id: int
    crm_id: str
    line_no: int
    supplier: OptCounterpartyResponse
    document_date: date
    amount: Decimal
    vat_amount: Decimal
    amount_without_vat: Decimal
    document_number: str | None = None


class OptVolumeCategoryBreakdown(BaseModel):
    label: str
    volume: Decimal
    rate_percent: Decimal
    commission: Decimal


class OptPaymentDocument(BaseModel):
    file_id: int
    name: str | None = None


class OptPaymentResponse(BaseModel):
    id: int
    amount: Decimal
    paid_at: datetime
    payment_type: str
    recipient: str
    created_at: datetime
    created_by: int
    created_by_name: str | None = None
    document_file_id: int | None = None
    document_name: str | None = None
    documents: list[OptPaymentDocument] = Field(default_factory=list)


class OptOrderPaymentCreateRequest(BaseModel):
    amount: Decimal = Field(gt=0)
    paid_at: datetime
    payment_type: Literal["card", "crypto", "wire", "cash"]
    recipient: Literal["orange", "beneficiary"]
    document_file_id: int | None = None
    document_file_ids: list[int] = Field(default_factory=list)


class OptCommissionAdjustRequest(BaseModel):
    amount: Decimal = Field(gt=0)
    direction: Literal["increase", "decrease"]


class OptCommissionHistoryItem(BaseModel):
    id: int
    old_commission_due: Decimal
    new_commission_due: Decimal
    delta: Decimal
    direction: str
    changed_by: int
    changed_by_name: str | None = None
    created_at: datetime


class OptOrderResponse(BaseModel):
    id: int
    lead_id: int
    order_no: int
    crm_id: str
    status: str
    payment_status: str
    vat_rate_percent: Decimal = Decimal("22")
    period_code: str | None = None
    total_volume: Decimal
    commission_base: Decimal
    commission_adjustment: Decimal
    commission_due: Decimal
    amount_paid: Decimal
    amount_remaining: Decimal
    volume_by_category: dict[str, OptVolumeCategoryBreakdown] = Field(default_factory=dict)
    buyer: OptCounterpartyResponse
    source_filename: str | None = None
    submission_error: str | None = None
    submitted_at: datetime | None = None
    created_at: datetime
    lines: list[OptOrderLineResponse] = Field(default_factory=list)
    payments: list[OptPaymentResponse] = Field(default_factory=list)
    commission_history: list[OptCommissionHistoryItem] = Field(default_factory=list)

    @field_validator("volume_by_category", mode="before")
    @classmethod
    def _coerce_volume_breakdown(cls, value: object) -> object:
        if not isinstance(value, dict):
            return {}
        parsed: dict[str, OptVolumeCategoryBreakdown] = {}
        for code, row in value.items():
            if isinstance(row, dict):
                parsed[str(code)] = OptVolumeCategoryBreakdown(
                    label=str(row.get("label") or code),
                    volume=Decimal(str(row.get("volume", 0))),
                    rate_percent=Decimal(str(row.get("rate_percent", 0))),
                    commission=Decimal(str(row.get("commission", 0))),
                )
        return parsed


class OptOrderListResponse(BaseModel):
    items: list[OptOrderResponse]


class OptOrderRegistryItem(BaseModel):
    id: int
    lead_id: int
    order_no: int
    chat_id: int | None = None
    contact_id: int | None = None
    contact_name: str | None = None
    group_id: int
    group_name: str | None = None
    department_id: int | None = None
    department_name: str | None = None
    manager_user_id: int | None = None
    manager_name: str | None = None
    status: str
    payment_status: str
    period_code: str | None = None
    total_volume: Decimal
    commission_due: Decimal
    amount_paid: Decimal
    amount_remaining: Decimal
    buyer: OptCounterpartyResponse
    source_filename: str | None = None
    created_at: datetime
    lines_count: int = 0
    payments_count: int = 0


class OptOrderRegistryListResponse(BaseModel):
    items: list[OptOrderRegistryItem]
    total: int


class OptPaymentLedgerItem(BaseModel):
    id: int
    order_id: int
    lead_id: int
    order_no: int
    chat_id: int | None = None
    contact_id: int | None = None
    contact_name: str | None = None
    group_id: int
    group_name: str | None = None
    department_id: int | None = None
    department_name: str | None = None
    manager_user_id: int | None = None
    manager_name: str | None = None
    period_code: str | None = None
    amount: Decimal
    paid_at: datetime
    payment_type: str
    recipient: str
    created_at: datetime
    created_by: int
    created_by_name: str | None = None
    document_file_id: int | None = None
    documents_count: int = 0
    order_payment_status: str
    order_commission_due: Decimal
    order_amount_paid: Decimal
    buyer: OptCounterpartyResponse


class OptPaymentLedgerListResponse(BaseModel):
    items: list[OptPaymentLedgerItem]
    total: int


class OptSendRegistryResponse(BaseModel):
    message_id: int
    chat_id: int


class OptOrderExistingRef(BaseModel):
    lead_id: int
    order_id: int
    order_no: int


class OptAttachmentProbeRequest(BaseModel):
    chat_id: int
    message_id: int
    attachment_index: int = Field(ge=0)


class OptAttachmentProbeResponse(BaseModel):
    is_application: bool
    buyer_inn: str | None = None
    line_count: int | None = None
    existing_order: OptOrderExistingRef | None = None


class OptUploadFromAttachmentRequest(BaseModel):
    chat_id: int
    message_id: int
    attachment_index: int = Field(ge=0)
    vat_rate_percent: Literal[20, 22] = 22
    # OPT period, e.g. "2/26". Overrides deal period when set.
    period_code: str | None = Field(default=None, max_length=16)


class OptOrderPeriodUpdateRequest(BaseModel):
    period_code: str = Field(min_length=1, max_length=16)


class OptOrderPeriodUpdateResponse(BaseModel):
    order_id: int
    lead_id: int
    period_code: str
