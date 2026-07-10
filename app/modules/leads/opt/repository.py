from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal

from app.modules.chats.timeutil import utc_now

from sqlalchemy import delete, select, func, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.db.models.lead_opt_order import LeadOptOrder, LeadOptOrderLine
from app.modules.db.models.lead_opt_order_commission_history import (
    LeadOptOrderCommissionHistory,
)
from app.modules.db.models.lead_opt_order_payment import LeadOptOrderPayment
from app.modules.db.models.opt_buyer import OptBuyer
from app.modules.db.models.opt_unit import OptUnit
from app.modules.db.models.uploaded_file import UploadedFile
from app.modules.leads.opt.pricing import (
    commission_base_from_breakdown,
    compute_order_pricing,
    payment_status,
)


class OptOrderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def new_crm_id(prefix: str) -> str:
        return f"{prefix}-{uuid.uuid4().hex[:12]}"

    async def get_unit_by_inn(self, inn: str) -> OptUnit | None:
        result = await self._session.execute(
            select(OptUnit).where(OptUnit.inn == inn, OptUnit.is_active.is_(True)),
        )
        return result.scalar_one_or_none()

    async def get_buyer_by_inn(self, inn: str) -> OptBuyer | None:
        result = await self._session.execute(
            select(OptBuyer).where(OptBuyer.inn == inn, OptBuyer.is_active.is_(True)),
        )
        return result.scalar_one_or_none()

    async def upsert_buyer(self, *, inn: str, kpp: str | None, name: str) -> OptBuyer:
        buyer = await self.get_buyer_by_inn(inn)
        if buyer is None:
            buyer = OptBuyer(inn=inn, kpp=kpp, name=name)
            self._session.add(buyer)
        else:
            buyer.kpp = kpp
            buyer.name = name
        await self._session.flush()
        return buyer

    async def update_unit_requisites(
        self,
        unit: OptUnit,
        *,
        kpp: str | None,
        name: str | None = None,
    ) -> None:
        if kpp:
            unit.kpp = kpp
        if name:
            unit.name = name
        await self._session.flush()

    async def list_units(self) -> list[OptUnit]:
        result = await self._session.execute(
            select(OptUnit).where(OptUnit.is_active.is_(True)).order_by(OptUnit.name),
        )
        return list(result.scalars().all())

    async def list_orders_for_lead(self, lead_id: int) -> list[LeadOptOrder]:
        result = await self._session.execute(
            select(LeadOptOrder)
            .where(LeadOptOrder.lead_id == lead_id)
            .options(
                selectinload(LeadOptOrder.lines),
                selectinload(LeadOptOrder.payments),
                selectinload(LeadOptOrder.commission_history).selectinload(
                    LeadOptOrderCommissionHistory.changer,
                ),
            )
            .order_by(LeadOptOrder.order_no.asc()),
        )
        return list(result.scalars().unique().all())

    async def get_order(self, order_id: int) -> LeadOptOrder | None:
        result = await self._session.execute(
            select(LeadOptOrder)
            .where(LeadOptOrder.id == order_id)
            .options(
                selectinload(LeadOptOrder.lines),
                selectinload(LeadOptOrder.payments),
                selectinload(LeadOptOrder.commission_history).selectinload(
                    LeadOptOrderCommissionHistory.changer,
                ),
            ),
        )
        return result.scalar_one_or_none()

    async def delete_order(self, order: LeadOptOrder) -> None:
        """Delete order via DB CASCADE; expunge ORM graph to avoid nulling child FKs on flush."""
        related = [
            order,
            *order.lines,
            *order.payments,
            *getattr(order, "commission_history", []) or [],
        ]
        for obj in related:
            if obj in self._session:
                self._session.expunge(obj)
        await self._session.execute(
            delete(LeadOptOrder).where(
                LeadOptOrder.id == order.id,
                LeadOptOrder.lead_id == order.lead_id,
            ),
        )

    async def get_units_by_inns(self, inns: list[str]) -> dict[str, OptUnit]:
        if not inns:
            return {}
        result = await self._session.execute(
            select(OptUnit).where(OptUnit.inn.in_(inns), OptUnit.is_active.is_(True)),
        )
        return {unit.inn: unit for unit in result.scalars().all()}

    async def apply_pricing_snapshot(self, order: LeadOptOrder) -> None:
        inns = [line.supplier_inn for line in order.lines]
        units = await self.get_units_by_inns(inns)
        total_volume, base_commission, breakdown = compute_order_pricing(order.lines, units)
        adjustment = Decimal(str(order.commission_adjustment or 0))
        commission_due = (base_commission + adjustment).quantize(Decimal("0.01"))
        order.total_volume = float(total_volume)
        order.commission_due = float(commission_due)
        order.volume_by_category = breakdown
        order.amount_paid = float(order.amount_paid or 0)
        order.payment_status = payment_status(
            Decimal(str(order.amount_paid)),
            commission_due,
        )

    async def apply_commission_adjustment(
        self,
        order: LeadOptOrder,
        *,
        delta: Decimal,
        changed_by: int,
    ) -> LeadOptOrderCommissionHistory:
        if delta == 0:
            raise ValueError("delta must be non-zero")
        current_adjustment = Decimal(str(order.commission_adjustment or 0))
        new_adjustment = (current_adjustment + delta).quantize(Decimal("0.01"))
        base_commission = commission_base_from_breakdown(order.volume_by_category)
        if base_commission == 0:
            base_commission = (
                Decimal(str(order.commission_due or 0)) - current_adjustment
            ).quantize(Decimal("0.01"))
        old_due = Decimal(str(order.commission_due or 0)).quantize(Decimal("0.01"))
        new_due = (base_commission + new_adjustment).quantize(Decimal("0.01"))
        amount_paid = Decimal(str(order.amount_paid or 0))
        order.commission_adjustment = float(new_adjustment)
        order.commission_due = float(new_due)
        order.payment_status = payment_status(amount_paid, new_due)
        history = LeadOptOrderCommissionHistory(
            order_id=order.id,
            old_commission_due=float(old_due),
            new_commission_due=float(new_due),
            delta=float(delta),
            direction="increase" if delta > 0 else "decrease",
            changed_by=changed_by,
        )
        self._session.add(history)
        await self._session.flush()
        return history

    async def add_payment(
        self,
        order: LeadOptOrder,
        *,
        amount: Decimal,
        paid_at: datetime,
        payment_type: str,
        recipient: str,
        created_by: int,
        document_file_id: int | None = None,
    ) -> LeadOptOrderPayment:
        payment = LeadOptOrderPayment(
            order_id=order.id,
            amount=float(amount),
            paid_at=paid_at,
            payment_type=payment_type,
            recipient=recipient,
            created_by=created_by,
            document_file_id=document_file_id,
        )
        self._session.add(payment)
        await self._session.flush()
        paid_total = Decimal(str(order.amount_paid or 0)) + amount
        order.amount_paid = float(paid_total)
        order.payment_status = payment_status(paid_total, Decimal(str(order.commission_due)))
        return payment

    async def get_uploaded_file(self, file_id: int) -> UploadedFile | None:
        result = await self._session.execute(
            select(UploadedFile).where(UploadedFile.id == file_id),
        )
        return result.scalar_one_or_none()

    async def get_payment(self, payment_id: int) -> LeadOptOrderPayment | None:
        result = await self._session.execute(
            select(LeadOptOrderPayment).where(LeadOptOrderPayment.id == payment_id),
        )
        return result.scalar_one_or_none()

    async def delete_line(self, order: LeadOptOrder, line_id: int) -> None:
        line = next((row for row in order.lines if row.id == line_id), None)
        if line is None:
            raise ValueError("line not found")
        if len(order.lines) <= 1:
            raise ValueError("cannot delete last line")
        await self._session.execute(
            delete(LeadOptOrderLine).where(LeadOptOrderLine.id == line_id),
        )
        await self._session.flush()
        await self._session.refresh(order, attribute_names=["lines"])
        for idx, remaining in enumerate(sorted(order.lines, key=lambda row: row.line_no), start=1):
            remaining.line_no = idx
        await self.apply_pricing_snapshot(order)

    _PENDING_SUBMISSION_STATUSES = frozenset({"draft", "queued", "submitting", "failed"})

    async def lead_has_pending_submission(self, lead_id: int) -> bool:
        result = await self._session.execute(
            select(LeadOptOrder.id).where(
                LeadOptOrder.lead_id == lead_id,
                LeadOptOrder.status.in_(self._PENDING_SUBMISSION_STATUSES),
            ).limit(1),
        )
        return result.scalar_one_or_none() is not None

    async def lead_has_unpaid_orders(self, lead_id: int) -> bool:
        result = await self._session.execute(
            select(LeadOptOrder.id).where(
                LeadOptOrder.lead_id == lead_id,
                LeadOptOrder.payment_status != "paid",
            ).limit(1),
        )
        return result.scalar_one_or_none() is not None

    async def get_order_by_crm_id(self, crm_id: str) -> LeadOptOrder | None:
        result = await self._session.execute(
            select(LeadOptOrder)
            .where(LeadOptOrder.crm_id == crm_id)
            .options(
                selectinload(LeadOptOrder.lines),
                selectinload(LeadOptOrder.payments),
            ),
        )
        return result.scalar_one_or_none()

    async def get_order_by_source_attachment(
        self,
        message_id: int,
        attachment_index: int,
    ) -> LeadOptOrder | None:
        result = await self._session.execute(
            select(LeadOptOrder)
            .where(
                LeadOptOrder.source_message_id == message_id,
                LeadOptOrder.source_attachment_index == attachment_index,
            )
            .options(
                selectinload(LeadOptOrder.lines),
                selectinload(LeadOptOrder.payments),
            ),
        )
        return result.scalar_one_or_none()

    async def get_order_by_content_fingerprint(self, fingerprint: str) -> LeadOptOrder | None:
        result = await self._session.execute(
            select(LeadOptOrder)
            .where(
                LeadOptOrder.content_fingerprint == fingerprint,
                LeadOptOrder.status.in_(("queued", "submitting", "submitted")),
            )
            .options(
                selectinload(LeadOptOrder.lines),
                selectinload(LeadOptOrder.payments),
            )
            .order_by(LeadOptOrder.id.desc())
            .limit(1),
        )
        return result.scalar_one_or_none()

    async def renumber_orders_for_lead(self, lead_id: int) -> None:
        """Dense 1..N numbering by created_at (after deletes gaps are closed)."""
        result = await self._session.execute(
            select(LeadOptOrder.id)
            .where(LeadOptOrder.lead_id == lead_id)
            .order_by(LeadOptOrder.created_at.asc(), LeadOptOrder.id.asc()),
        )
        order_ids = [int(row[0]) for row in result.all()]
        for idx, order_id in enumerate(order_ids, start=1):
            await self._session.execute(
                update(LeadOptOrder)
                .where(LeadOptOrder.id == order_id)
                .values(order_no=idx),
            )
        await self._session.flush()

    async def next_order_no(self, lead_id: int) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(LeadOptOrder)
            .where(LeadOptOrder.lead_id == lead_id),
        )
        return int(result.scalar_one()) + 1

    async def create_order(
        self,
        *,
        lead_id: int,
        crm_id: str,
        buyer_inn: str,
        buyer_kpp: str | None,
        buyer_name: str | None,
        source_filename: str | None,
        created_by: int,
        lines: list[dict[str, object]],
        source_message_id: int | None = None,
        source_attachment_index: int | None = None,
        content_fingerprint: str | None = None,
    ) -> LeadOptOrder:
        order_no = await self.next_order_no(lead_id)
        order = LeadOptOrder(
            lead_id=lead_id,
            crm_id=crm_id,
            order_no=order_no,
            buyer_inn=buyer_inn,
            buyer_kpp=buyer_kpp,
            buyer_name=buyer_name,
            status="queued",
            source_filename=source_filename,
            source_message_id=source_message_id,
            source_attachment_index=source_attachment_index,
            content_fingerprint=content_fingerprint,
            created_by=created_by,
        )
        self._session.add(order)
        await self._session.flush()

        for idx, line_data in enumerate(lines, start=1):
            line = LeadOptOrderLine(
                order_id=order.id,
                crm_id=str(line_data["crm_id"]),
                line_no=idx,
                supplier_inn=str(line_data["supplier_inn"]),
                supplier_kpp=line_data.get("supplier_kpp"),  # type: ignore[arg-type]
                supplier_name=line_data.get("supplier_name"),  # type: ignore[arg-type]
                document_date=line_data["document_date"],  # type: ignore[arg-type]
                amount=line_data["amount"],  # type: ignore[arg-type]
                vat_amount=line_data["vat_amount"],  # type: ignore[arg-type]
                amount_without_vat=line_data["amount_without_vat"],  # type: ignore[arg-type]
            )
            self._session.add(line)

        await self._session.flush()
        await self._session.refresh(order, attribute_names=["lines"])
        await self.apply_pricing_snapshot(order)
        return order

    async def mark_submitting(self, order: LeadOptOrder) -> None:
        order.status = "submitting"
        order.submission_error = None

    async def mark_queued(self, order: LeadOptOrder) -> None:
        order.status = "queued"
        order.submission_error = None

    async def mark_submitted(
        self,
        order: LeadOptOrder,
        *,
        actor_id: int,
        request_payload: dict[str, object],
        response_payload: dict[str, object],
        line_numbers: dict[str, str],
    ) -> None:
        now = utc_now()
        order.status = "submitted"
        order.submitted_at = now
        order.submitted_by = actor_id
        order.submission_request = request_payload
        order.submission_response = response_payload
        order.submission_error = None
        for line in order.lines:
            doc_no = line_numbers.get(line.crm_id)
            if doc_no:
                line.document_number = doc_no

    async def mark_failed(
        self,
        order: LeadOptOrder,
        *,
        actor_id: int,
        request_payload: dict[str, object] | None,
        error_message: str,
        response_payload: dict[str, object] | None = None,
    ) -> None:
        order.status = "failed"
        order.submitted_at = utc_now()
        order.submitted_by = actor_id
        order.submission_request = request_payload
        order.submission_response = response_payload
        order.submission_error = error_message[:2000]

    async def list_ids_by_status(self, *statuses: str) -> list[int]:
        if not statuses:
            return []
        result = await self._session.execute(
            select(LeadOptOrder.id)
            .where(LeadOptOrder.status.in_(statuses))
            .order_by(LeadOptOrder.id.asc()),
        )
        return [int(row) for row in result.scalars()]

    async def recover_stale_submitting(self, *, minutes: int = 15) -> list[int]:
        cutoff = utc_now() - timedelta(minutes=minutes)
        result = await self._session.execute(
            select(LeadOptOrder).where(
                LeadOptOrder.status == "submitting",
                LeadOptOrder.updated_at < cutoff,
            ),
        )
        recovered: list[int] = []
        for order in result.scalars():
            order.status = "queued"
            order.submission_error = None
            recovered.append(int(order.id))
        if recovered:
            await self._session.flush()
        return recovered

    async def save(self, entity: LeadOptOrder | LeadOptOrderLine | LeadOptOrderPayment | OptUnit) -> None:
        self._session.add(entity)
        await self._session.flush()
