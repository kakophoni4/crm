from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.db.models.lead_opt_order import LeadOptOrder, LeadOptOrderLine
from app.modules.db.models.lead_opt_order_payment import LeadOptOrderPayment
from app.modules.db.models.opt_unit import OptUnit
from app.modules.leads.opt.pricing import compute_order_pricing, payment_status


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
            ),
        )
        return result.scalar_one_or_none()

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
        total_volume, commission_due, breakdown = compute_order_pricing(order.lines, units)
        order.total_volume = float(total_volume)
        order.commission_due = float(commission_due)
        order.volume_by_category = breakdown
        order.amount_paid = float(order.amount_paid or 0)
        order.payment_status = payment_status(
            Decimal(str(order.amount_paid)),
            Decimal(str(order.commission_due)),
        )

    async def add_payment(
        self,
        order: LeadOptOrder,
        *,
        amount: Decimal,
        paid_at: datetime,
        payment_type: str,
        recipient: str,
        created_by: int,
    ) -> LeadOptOrderPayment:
        payment = LeadOptOrderPayment(
            order_id=order.id,
            amount=float(amount),
            paid_at=paid_at,
            payment_type=payment_type,
            recipient=recipient,
            created_by=created_by,
        )
        self._session.add(payment)
        await self._session.flush()
        paid_total = Decimal(str(order.amount_paid or 0)) + amount
        order.amount_paid = float(paid_total)
        order.payment_status = payment_status(paid_total, Decimal(str(order.commission_due)))
        return payment

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

    async def next_order_no(self, lead_id: int) -> int:
        result = await self._session.execute(
            select(func.coalesce(func.max(LeadOptOrder.order_no), 0)).where(
                LeadOptOrder.lead_id == lead_id,
            ),
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
        now = datetime.now(UTC)
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
        order.submitted_at = datetime.now(UTC)
        order.submitted_by = actor_id
        order.submission_request = request_payload
        order.submission_response = response_payload
        order.submission_error = error_message[:2000]

    async def save(self, entity: LeadOptOrder | LeadOptOrderLine | LeadOptOrderPayment | OptUnit) -> None:
        self._session.add(entity)
        await self._session.flush()
