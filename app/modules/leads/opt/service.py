from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.contacts.scope_loader import ScopeLoader
from app.modules.db.models.lead import Lead
from app.modules.db.models.lead_opt_order import LeadOptOrder, LeadOptOrderLine
from app.modules.db.models.lead_opt_order_payment import LeadOptOrderPayment
from app.modules.db.models.user import User
from sqlalchemy.orm import selectinload
from app.modules.leads.access import actor_can_access_lead
from app.modules.leads.opt.mole_client import (
    MoleApiError,
    delete_order as mole_delete_order,
    filter_orders as mole_filter_orders,
    get_order as mole_get_order,
    mole_session,
    post_opt_order,
    put_order as mole_put_order,
)
from app.modules.leads.opt.requisites import ensure_unit_requisites, resolve_buyer_requisites
from app.modules.leads.opt.fingerprint import compute_application_fingerprint
from app.modules.leads.opt.parser import parse_application_workbook
from app.modules.leads.opt.queue import dequeue_opt_submit, enqueue_opt_submit
from app.modules.leads.opt.registry_export import build_registry_workbook
from app.modules.leads.opt.repository import OptOrderRepository
from app.modules.leads.opt.sync_diff import mole_is_deleted, plan_sync_actions, registries_match
from app.modules.leads.opt.schemas import (
    OptAttachmentProbeResponse,
    OptCommissionHistoryItem,
    OptCounterpartyResponse,
    OptOrderExistingRef,
    OptOrderLineResponse,
    OptOrderListResponse,
    OptOrderPaymentCreateRequest,
    OptCommissionAdjustRequest,
    OptOrderRegistryItem,
    OptOrderRegistryListResponse,
    OptOrderResponse,
    OptPaymentDocument,
    OptPaymentLedgerItem,
    OptPaymentLedgerListResponse,
    OptPaymentResponse,
    OptRegistryManagerItem,
    OptRegistryManagersResponse,
    OptSync1cActionItem,
    OptSync1cResponse,
    OptVolumeCategoryBreakdown,
)
from app.modules.leads.opt.pricing import commission_base_from_breakdown
from app.modules.leads.opt.periods import (
    normalize_period_code,
    period_code_to_mole_iso,
    read_lead_opt_period,
)
from app.modules.leads.opt.vat import normalize_opt_vat_rate, split_vat_included
from app.modules.leads.repository import LeadRepository
from app.modules.rbac.role_checks import is_admin
from app.realtime.events import publish
from app.shared.exceptions import NotFound, PermissionDenied, ValidationError
from app.shared.settings import get_settings

logger = structlog.get_logger(__name__)

OPT_SERVICE_NAME = "ОПТ"

_SPREADSHEET_MIMES = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
)
_SPREADSHEET_EXTS = (".xlsx", ".xls")


def _looks_like_spreadsheet(filename: str | None, content_type: str | None) -> bool:
    if content_type:
        lowered = content_type.lower()
        if any(token in lowered for token in ("spreadsheet", "ms-excel", "excel")):
            return True
    if filename:
        name = filename.lower()
        if any(name.endswith(ext) for ext in _SPREADSHEET_EXTS):
            return True
    return False


def _existing_order_ref(order: LeadOptOrder) -> OptOrderExistingRef:
    return OptOrderExistingRef(
        lead_id=order.lead_id,
        order_id=order.id,
        order_no=order.order_no,
    )


def duplicate_order_message(order: LeadOptOrder) -> str:
    return (
        f"Такая заявка уже существует по сделке №{order.lead_id}, "
        f"заявка №{order.order_no}"
    )


class OptOrderService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = OptOrderRepository(session)
        self._leads = LeadRepository(session)
        self._scope_loader = ScopeLoader(session)

    async def _get_lead_for_actor(self, actor: User, lead_id: int) -> Lead:
        lead = await self._leads.get_by_id(lead_id)
        if lead is None:
            raise NotFound(message="Lead not found")
        ctx = await self._scope_loader.load(actor)
        if not await actor_can_access_lead(self._session, ctx, lead):
            raise NotFound(message="Lead not found")
        return lead

    async def _get_order_for_actor(self, actor: User, lead_id: int, order_id: int) -> LeadOptOrder:
        await self._get_lead_for_actor(actor, lead_id)
        order = await self._repo.get_order(order_id)
        if order is None or order.lead_id != lead_id or order.deleted_at is not None:
            raise NotFound(message="OPT order not found")
        return order

    def _to_response(
        self,
        order: LeadOptOrder,
        *,
        document_names: dict[int, str] | None = None,
    ) -> OptOrderResponse:
        commission_due = Decimal(str(order.commission_due or 0))
        commission_adjustment = Decimal(str(order.commission_adjustment or 0))
        commission_base = commission_base_from_breakdown(order.volume_by_category)
        if commission_base == 0:
            commission_base = (commission_due - commission_adjustment).quantize(Decimal("0.01"))
        amount_paid = Decimal(str(order.amount_paid or 0))
        remaining = max(Decimal("0"), commission_due - amount_paid).quantize(Decimal("0.01"))
        breakdown: dict[str, OptVolumeCategoryBreakdown] = {}
        raw_breakdown = order.volume_by_category or {}
        if isinstance(raw_breakdown, dict):
            for code, row in raw_breakdown.items():
                if isinstance(row, dict):
                    breakdown[str(code)] = OptVolumeCategoryBreakdown(
                        label=str(row.get("label") or code),
                        volume=Decimal(str(row.get("volume", 0))),
                        rate_percent=Decimal(str(row.get("rate_percent", 0))),
                        commission=Decimal(str(row.get("commission", 0))),
                    )
        names = document_names or {}
        history_rows = getattr(order, "commission_history", None) or []
        return OptOrderResponse(
            id=order.id,
            lead_id=order.lead_id,
            order_no=order.order_no,
            crm_id=order.crm_id,
            status=order.status,
            payment_status=order.payment_status or "unpaid",
            vat_rate_percent=Decimal(str(getattr(order, "vat_rate_percent", None) or 22)),
            period_code=getattr(order, "period_code", None),
            total_volume=Decimal(str(order.total_volume or 0)),
            commission_base=commission_base,
            commission_adjustment=commission_adjustment,
            commission_due=commission_due,
            amount_paid=amount_paid,
            amount_remaining=remaining,
            volume_by_category=breakdown,
            buyer=OptCounterpartyResponse(
                inn=order.buyer_inn,
                kpp=order.buyer_kpp,
                name=order.buyer_name,
            ),
            source_filename=order.source_filename,
            submission_error=order.submission_error,
            submitted_at=order.submitted_at,
            created_at=order.created_at,
            lines=[
                OptOrderLineResponse(
                    id=line.id,
                    crm_id=line.crm_id,
                    line_no=line.line_no,
                    supplier=OptCounterpartyResponse(
                        inn=line.supplier_inn,
                        kpp=line.supplier_kpp,
                        name=line.supplier_name,
                    ),
                    document_date=line.document_date,
                    amount=Decimal(str(line.amount)),
                    vat_amount=Decimal(str(line.vat_amount)),
                    amount_without_vat=Decimal(str(line.amount_without_vat)),
                    document_number=line.document_number,
                )
                for line in sorted(order.lines, key=lambda row: row.line_no)
            ],
            payments=[
                self._payment_to_response(payment, names)
                for payment in sorted(order.payments, key=lambda row: row.paid_at)
            ],
            commission_history=[
                OptCommissionHistoryItem(
                    id=row.id,
                    old_commission_due=Decimal(str(row.old_commission_due)),
                    new_commission_due=Decimal(str(row.new_commission_due)),
                    delta=Decimal(str(row.delta)),
                    direction=row.direction,
                    changed_by=row.changed_by,
                    changed_by_name=row.changer.full_name if row.changer is not None else None,
                    created_at=row.created_at,
                )
                for row in sorted(history_rows, key=lambda item: item.created_at, reverse=True)
            ],
        )

    @staticmethod
    def _payment_document_ids(payment: object) -> list[int]:
        raw_ids = getattr(payment, "document_file_ids", None) or []
        ids: list[int] = []
        for value in raw_ids:
            try:
                file_id = int(value)
            except (TypeError, ValueError):
                continue
            if file_id not in ids:
                ids.append(file_id)
        legacy = getattr(payment, "document_file_id", None)
        if legacy is not None:
            try:
                legacy_id = int(legacy)
            except (TypeError, ValueError):
                legacy_id = None
            if legacy_id is not None and legacy_id not in ids:
                ids.insert(0, legacy_id)
        return ids

    def _payment_to_response(
        self,
        payment: object,
        names: dict[int, str],
    ) -> OptPaymentResponse:
        doc_ids = self._payment_document_ids(payment)
        primary_id = doc_ids[0] if doc_ids else None
        creator = getattr(payment, "creator", None)
        created_by = int(getattr(payment, "created_by"))
        return OptPaymentResponse(
            id=int(getattr(payment, "id")),
            amount=Decimal(str(getattr(payment, "amount"))),
            paid_at=getattr(payment, "paid_at"),
            payment_type=str(getattr(payment, "payment_type")),
            recipient=str(getattr(payment, "recipient")),
            created_at=getattr(payment, "created_at"),
            created_by=created_by,
            created_by_name=creator.full_name if creator is not None else None,
            document_file_id=primary_id,
            document_name=names.get(primary_id) if primary_id is not None else None,
            documents=[
                OptPaymentDocument(file_id=file_id, name=names.get(file_id))
                for file_id in doc_ids
            ],
        )

    async def _document_names_for_orders(
        self,
        orders: list[LeadOptOrder],
    ) -> dict[int, str]:
        file_ids: set[int] = set()
        for order in orders:
            for payment in order.payments:
                file_ids.update(self._payment_document_ids(payment))
        if not file_ids:
            return {}
        from sqlalchemy import select

        from app.modules.db.models.uploaded_file import UploadedFile

        result = await self._session.execute(
            select(UploadedFile.id, UploadedFile.original_name).where(
                UploadedFile.id.in_(file_ids),
            ),
        )
        return {int(row[0]): str(row[1]) for row in result.all()}

    async def _to_response_async(self, order: LeadOptOrder) -> OptOrderResponse:
        names = await self._document_names_for_orders([order])
        return self._to_response(order, document_names=names)

    async def add_payment(
        self,
        actor: User,
        lead_id: int,
        order_id: int,
        body: OptOrderPaymentCreateRequest,
    ) -> OptOrderResponse:
        order = await self._get_order_for_actor(actor, lead_id, order_id)
        remaining = Decimal(str(order.commission_due or 0)) - Decimal(str(order.amount_paid or 0))
        if body.amount > remaining + Decimal("0.01"):
            raise ValidationError(
                message=f"Сумма оплаты превышает остаток ({remaining.quantize(Decimal('0.01'))} ₽)",
            )
        doc_ids: list[int] = []
        for file_id in [*body.document_file_ids, body.document_file_id]:
            if file_id is None:
                continue
            try:
                normalized = int(file_id)
            except (TypeError, ValueError):
                continue
            if normalized not in doc_ids:
                doc_ids.append(normalized)
        if body.payment_type != "cash" and not doc_ids:
            raise ValidationError(
                message="Прикрепите документ подтверждения оплаты (для наличных не требуется)",
            )
        for file_id in doc_ids:
            uploaded = await self._repo.get_uploaded_file(file_id)
            if uploaded is None:
                raise ValidationError(message=f"Файл платёжного документа #{file_id} не найден")
        await self._repo.add_payment(
            order,
            amount=body.amount,
            paid_at=body.paid_at,
            payment_type=body.payment_type,
            recipient=body.recipient,
            created_by=actor.id,
            document_file_id=doc_ids[0] if doc_ids else None,
            document_file_ids=doc_ids,
        )
        await self._session.commit()
        refreshed = await self._repo.get_order(order.id)
        assert refreshed is not None
        return await self._to_response_async(refreshed)

    async def adjust_commission(
        self,
        actor: User,
        lead_id: int,
        order_id: int,
        body: OptCommissionAdjustRequest,
    ) -> OptOrderResponse:
        order = await self._get_order_for_actor(actor, lead_id, order_id)
        if order.payment_status == "paid":
            raise ValidationError(message="Нельзя менять сумму полностью оплаченной заявки")

        current_adjustment = Decimal(str(order.commission_adjustment or 0))
        base_commission = commission_base_from_breakdown(order.volume_by_category)
        if base_commission == 0:
            base_commission = (
                Decimal(str(order.commission_due or 0)) - current_adjustment
            ).quantize(Decimal("0.01"))

        delta = body.amount if body.direction == "increase" else -body.amount
        new_adjustment = (current_adjustment + delta).quantize(Decimal("0.01"))
        new_due = (base_commission + new_adjustment).quantize(Decimal("0.01"))
        amount_paid = Decimal(str(order.amount_paid or 0))

        if new_due < 0:
            raise ValidationError(message="Сумма к оплате не может быть отрицательной")
        if new_due + Decimal("0.01") < amount_paid:
            raise ValidationError(
                message="Сумма к оплате не может быть меньше уже оплаченной суммы",
            )

        await self._repo.apply_commission_adjustment(
            order,
            delta=delta,
            changed_by=actor.id,
        )
        await self._session.commit()
        # Expire so get_order reloads history (+ changer) instead of identity-map cache.
        self._session.expire(order, ["commission_history"])
        refreshed = await self._repo.get_order(order.id)
        assert refreshed is not None
        return await self._to_response_async(refreshed)

    async def delete_line(
        self,
        actor: User,
        lead_id: int,
        order_id: int,
        line_id: int,
    ) -> OptOrderResponse:
        order = await self._get_order_for_actor(actor, lead_id, order_id)
        if len(order.lines) <= 1:
            raise ValidationError(
                message="Нельзя удалить единственную фактуру — удалите всю заявку",
            )
        line = next((row for row in order.lines if row.id == line_id), None)
        if line is None:
            raise NotFound(message="Фактура не найдена")

        await self._repo.delete_line(order, line_id)
        await self._session.commit()
        refreshed = await self._repo.get_order(order.id)
        assert refreshed is not None
        return await self._to_response_async(refreshed)

    async def get_payment_document(
        self,
        actor: User,
        lead_id: int,
        order_id: int,
        payment_id: int,
        *,
        file_id: int | None = None,
    ) -> tuple[bytes, str, str]:
        from app.modules.files.service import FilesService

        order = await self._get_order_for_actor(actor, lead_id, order_id)
        payment = next((row for row in order.payments if row.id == payment_id), None)
        if payment is None:
            raise NotFound(message="Платёжный документ не найден")
        doc_ids = self._payment_document_ids(payment)
        if not doc_ids:
            raise NotFound(message="Платёжный документ не найден")
        target_id = file_id if file_id is not None else doc_ids[0]
        if target_id not in doc_ids:
            raise NotFound(message="Платёжный документ не найден")
        files = FilesService(self._session)
        return await files.get_bytes(target_id)

    async def list_registry(
        self,
        actor: User,
        *,
        department_id: int | None = None,
        group_id: int | None = None,
        contact_id: int | None = None,
        chat_id: int | None = None,
        payment_status: str | None = None,
        period_code: str | None = None,
        manager_user_id: int | None = None,
        open_only: bool = False,
        offset: int = 0,
        limit: int = 50,
    ) -> OptOrderRegistryListResponse:
        from sqlalchemy import func, select

        from app.modules.db.models.contact import Contact
        from app.modules.db.models.contact_group_assignment import ContactGroupAssignment
        from app.modules.db.models.department import Department
        from app.modules.db.models.group import Group
        from app.modules.db.models.lead import Lead
        from app.modules.rbac.scope import SCOPE_ALL, visible_group_ids

        from app.modules.db.models.enums import UserRole

        ctx = await self._scope_loader.load(actor)
        scoped = visible_group_ids(ctx)
        if scoped != SCOPE_ALL and not scoped:
            return OptOrderRegistryListResponse(
                items=[],
                total=0,
                total_volume_sum=Decimal("0"),
                commission_due_sum=Decimal("0"),
                amount_paid_sum=Decimal("0"),
            )

        role = (
            actor.role
            if isinstance(actor.role, UserRole)
            else UserRole(str(actor.role))
        )

        filters = []
        if scoped != SCOPE_ALL:
            filters.append(Lead.group_id.in_(scoped))
        if department_id is not None:
            filters.append(Group.department_id == department_id)
        if group_id is not None:
            filters.append(Lead.group_id == group_id)
        if contact_id is not None:
            filters.append(Lead.contact_id == contact_id)
        if chat_id is not None:
            filters.append(Lead.chat_id == chat_id)
        if payment_status:
            statuses = [part.strip() for part in payment_status.split(",") if part.strip()]
            if len(statuses) == 1:
                filters.append(LeadOptOrder.payment_status == statuses[0])
            elif statuses:
                filters.append(LeadOptOrder.payment_status.in_(statuses))
        if period_code:
            filters.append(LeadOptOrder.period_code == period_code.strip())
        # Operators see only their own cards; seniors/admins keep group/dept/all scope.
        if role == UserRole.USER:
            filters.append(ContactGroupAssignment.owner_user_id == actor.id)
        elif manager_user_id is not None:
            filters.append(ContactGroupAssignment.owner_user_id == manager_user_id)
        if open_only:
            filters.append(Lead.closed_at.is_(None))

        filters.append(LeadOptOrder.deleted_at.is_(None))

        manager_join = (
            ContactGroupAssignment,
            (ContactGroupAssignment.contact_id == Lead.contact_id)
            & (ContactGroupAssignment.group_id == Lead.group_id),
        )

        stats_stmt = (
            select(
                func.count(),
                func.coalesce(func.sum(LeadOptOrder.total_volume), 0),
                func.coalesce(func.sum(LeadOptOrder.commission_due), 0),
                func.coalesce(func.sum(LeadOptOrder.amount_paid), 0),
            )
            .select_from(LeadOptOrder)
            .join(Lead, Lead.id == LeadOptOrder.lead_id)
            .join(Group, Group.id == Lead.group_id)
            .outerjoin(*manager_join)
        )
        if filters:
            stats_stmt = stats_stmt.where(*filters)
        total_raw, volume_raw, due_raw, paid_raw = (
            await self._session.execute(stats_stmt)
        ).one()
        total = int(total_raw or 0)
        total_volume_sum = Decimal(str(volume_raw or 0)).quantize(Decimal("0.01"))
        commission_due_sum = Decimal(str(due_raw or 0)).quantize(Decimal("0.01"))
        amount_paid_sum = Decimal(str(paid_raw or 0)).quantize(Decimal("0.01"))

        stmt = (
            select(
                LeadOptOrder,
                Lead.chat_id,
                Lead.contact_id,
                Lead.group_id,
                Contact.full_name,
                Group.name,
                Group.department_id,
                Department.name,
                User.id,
                User.full_name,
            )
            .join(Lead, Lead.id == LeadOptOrder.lead_id)
            .join(Group, Group.id == Lead.group_id)
            .outerjoin(Department, Department.id == Group.department_id)
            .outerjoin(Contact, Contact.id == Lead.contact_id)
            .outerjoin(*manager_join)
            .outerjoin(User, User.id == ContactGroupAssignment.owner_user_id)
            .options(
                selectinload(LeadOptOrder.lines),
                selectinload(LeadOptOrder.payments).selectinload(
                    LeadOptOrderPayment.creator,
                ),
            )
        )
        if filters:
            stmt = stmt.where(*filters)

        result = await self._session.execute(
            stmt.order_by(LeadOptOrder.created_at.desc(), LeadOptOrder.id.desc())
            .offset(offset)
            .limit(limit),
        )
        items: list[OptOrderRegistryItem] = []
        for (
            order,
            chat_id_row,
            contact_id_row,
            order_group_id,
            contact_name,
            group_name,
            dept_id,
            dept_name,
            manager_id,
            manager_name,
        ) in result.all():
            commission_due = Decimal(str(order.commission_due or 0))
            amount_paid = Decimal(str(order.amount_paid or 0))
            remaining = max(Decimal("0"), commission_due - amount_paid).quantize(Decimal("0.01"))
            items.append(
                OptOrderRegistryItem(
                    id=order.id,
                    lead_id=order.lead_id,
                    order_no=order.order_no,
                    chat_id=chat_id_row,
                    contact_id=contact_id_row,
                    contact_name=contact_name,
                    group_id=order_group_id,
                    group_name=group_name,
                    department_id=dept_id,
                    department_name=dept_name,
                    manager_user_id=manager_id,
                    manager_name=manager_name,
                    status=order.status,
                    payment_status=order.payment_status or "unpaid",
                    period_code=getattr(order, "period_code", None),
                    total_volume=Decimal(str(order.total_volume or 0)),
                    commission_due=commission_due,
                    amount_paid=amount_paid,
                    amount_remaining=remaining,
                    buyer=OptCounterpartyResponse(
                        inn=order.buyer_inn,
                        kpp=order.buyer_kpp,
                        name=order.buyer_name,
                    ),
                    source_filename=order.source_filename,
                    created_at=order.created_at,
                    lines_count=len(order.lines),
                    payments_count=len(order.payments),
                ),
            )
        return OptOrderRegistryListResponse(
            items=items,
            total=total,
            total_volume_sum=total_volume_sum,
            commission_due_sum=commission_due_sum,
            amount_paid_sum=amount_paid_sum,
        )

    async def list_registry_managers(
        self,
        actor: User,
        *,
        department_id: int | None = None,
        group_id: int | None = None,
        period_code: str | None = None,
    ) -> OptRegistryManagersResponse:
        """Distinct card owners that appear on at least one OPT order in scope."""
        from sqlalchemy import select

        from app.modules.db.models.contact_group_assignment import ContactGroupAssignment
        from app.modules.db.models.group import Group
        from app.modules.db.models.lead import Lead
        from app.modules.rbac.scope import SCOPE_ALL, visible_group_ids

        ctx = await self._scope_loader.load(actor)
        scoped = visible_group_ids(ctx)
        if scoped != SCOPE_ALL and not scoped:
            return OptRegistryManagersResponse(items=[])

        filters = [
            ContactGroupAssignment.owner_user_id.is_not(None),
            LeadOptOrder.deleted_at.is_(None),
        ]
        if scoped != SCOPE_ALL:
            filters.append(Lead.group_id.in_(scoped))
        if department_id is not None:
            filters.append(Group.department_id == department_id)
        if group_id is not None:
            filters.append(Lead.group_id == group_id)
        if period_code:
            filters.append(LeadOptOrder.period_code == period_code.strip())

        stmt = (
            select(User.id, User.full_name)
            .select_from(LeadOptOrder)
            .join(Lead, Lead.id == LeadOptOrder.lead_id)
            .join(Group, Group.id == Lead.group_id)
            .join(
                ContactGroupAssignment,
                (ContactGroupAssignment.contact_id == Lead.contact_id)
                & (ContactGroupAssignment.group_id == Lead.group_id),
            )
            .join(User, User.id == ContactGroupAssignment.owner_user_id)
            .where(*filters)
            .distinct()
            .order_by(User.full_name.asc().nulls_last(), User.id.asc())
        )
        rows = (await self._session.execute(stmt)).all()
        return OptRegistryManagersResponse(
            items=[
                OptRegistryManagerItem(id=int(user_id), full_name=full_name)
                for user_id, full_name in rows
            ],
        )

    async def list_payments_ledger(
        self,
        actor: User,
        *,
        department_id: int | None = None,
        group_id: int | None = None,
        contact_id: int | None = None,
        payment_type: str | None = None,
        payment_status: str | None = None,
        period_code: str | None = None,
        manager_user_id: int | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> OptPaymentLedgerListResponse:
        from sqlalchemy import func, select

        from app.modules.db.models.contact import Contact
        from app.modules.db.models.contact_group_assignment import ContactGroupAssignment
        from app.modules.db.models.department import Department
        from app.modules.db.models.group import Group
        from app.modules.db.models.lead import Lead
        from app.modules.rbac.scope import SCOPE_ALL, visible_group_ids

        ctx = await self._scope_loader.load(actor)
        scoped = visible_group_ids(ctx)
        if scoped != SCOPE_ALL and not scoped:
            return OptPaymentLedgerListResponse(items=[], total=0)

        filters = []
        if scoped != SCOPE_ALL:
            filters.append(Lead.group_id.in_(scoped))
        if department_id is not None:
            filters.append(Group.department_id == department_id)
        if group_id is not None:
            filters.append(Lead.group_id == group_id)
        if contact_id is not None:
            filters.append(Lead.contact_id == contact_id)
        if payment_type:
            types = [part.strip() for part in payment_type.split(",") if part.strip()]
            if len(types) == 1:
                filters.append(LeadOptOrderPayment.payment_type == types[0])
            elif types:
                filters.append(LeadOptOrderPayment.payment_type.in_(types))
        if payment_status:
            statuses = [part.strip() for part in payment_status.split(",") if part.strip()]
            if len(statuses) == 1:
                filters.append(LeadOptOrder.payment_status == statuses[0])
            elif statuses:
                filters.append(LeadOptOrder.payment_status.in_(statuses))
        if period_code:
            filters.append(LeadOptOrder.period_code == period_code.strip())
        if manager_user_id is not None:
            filters.append(ContactGroupAssignment.owner_user_id == manager_user_id)

        filters.append(LeadOptOrder.deleted_at.is_(None))

        manager_join = (
            ContactGroupAssignment,
            (ContactGroupAssignment.contact_id == Lead.contact_id)
            & (ContactGroupAssignment.group_id == Lead.group_id),
        )

        count_stmt = (
            select(func.count())
            .select_from(LeadOptOrderPayment)
            .join(LeadOptOrder, LeadOptOrder.id == LeadOptOrderPayment.order_id)
            .join(Lead, Lead.id == LeadOptOrder.lead_id)
            .join(Group, Group.id == Lead.group_id)
            .outerjoin(*manager_join)
        )
        if filters:
            count_stmt = count_stmt.where(*filters)
        total = int((await self._session.execute(count_stmt)).scalar_one())

        stmt = (
            select(
                LeadOptOrderPayment,
                LeadOptOrder,
                Lead.chat_id,
                Lead.contact_id,
                Lead.group_id,
                Contact.full_name,
                Group.name,
                Group.department_id,
                Department.name,
                User.id,
                User.full_name,
            )
            .join(LeadOptOrder, LeadOptOrder.id == LeadOptOrderPayment.order_id)
            .join(Lead, Lead.id == LeadOptOrder.lead_id)
            .join(Group, Group.id == Lead.group_id)
            .outerjoin(Department, Department.id == Group.department_id)
            .outerjoin(Contact, Contact.id == Lead.contact_id)
            .outerjoin(*manager_join)
            .outerjoin(User, User.id == ContactGroupAssignment.owner_user_id)
            .options(selectinload(LeadOptOrderPayment.creator))
        )
        if filters:
            stmt = stmt.where(*filters)

        result = await self._session.execute(
            stmt.order_by(LeadOptOrderPayment.paid_at.desc(), LeadOptOrderPayment.id.desc())
            .offset(offset)
            .limit(limit),
        )
        items: list[OptPaymentLedgerItem] = []
        for (
            payment,
            order,
            chat_id_row,
            contact_id_row,
            order_group_id,
            contact_name,
            group_name,
            dept_id,
            dept_name,
            manager_id,
            manager_name,
        ) in result.all():
            doc_ids = self._payment_document_ids(payment)
            creator = payment.creator
            items.append(
                OptPaymentLedgerItem(
                    id=payment.id,
                    order_id=order.id,
                    lead_id=order.lead_id,
                    order_no=order.order_no,
                    chat_id=chat_id_row,
                    contact_id=contact_id_row,
                    contact_name=contact_name,
                    group_id=order_group_id,
                    group_name=group_name,
                    department_id=dept_id,
                    department_name=dept_name,
                    manager_user_id=manager_id,
                    manager_name=manager_name,
                    period_code=getattr(order, "period_code", None),
                    amount=Decimal(str(payment.amount)),
                    paid_at=payment.paid_at,
                    payment_type=payment.payment_type,
                    recipient=payment.recipient,
                    created_at=payment.created_at,
                    created_by=payment.created_by,
                    created_by_name=creator.full_name if creator is not None else None,
                    document_file_id=doc_ids[0] if doc_ids else None,
                    documents_count=len(doc_ids),
                    order_payment_status=order.payment_status or "unpaid",
                    order_commission_due=Decimal(str(order.commission_due or 0)),
                    order_amount_paid=Decimal(str(order.amount_paid or 0)),
                    buyer=OptCounterpartyResponse(
                        inn=order.buyer_inn,
                        kpp=order.buyer_kpp,
                        name=order.buyer_name,
                    ),
                ),
            )
        return OptPaymentLedgerListResponse(items=items, total=total)

    @staticmethod
    async def assert_lead_won_payment_allowed(
        session: AsyncSession,
        lead_id: int,
        service_name: str | None,
    ) -> None:
        from app.modules.leads.opt.payment_guard import assert_lead_won_payment_allowed

        await assert_lead_won_payment_allowed(session, lead_id, service_name)

    async def list_orders(self, actor: User, lead_id: int) -> OptOrderListResponse:
        await self._get_lead_for_actor(actor, lead_id)
        orders = await self._repo.list_orders_for_lead(lead_id)
        names = await self._document_names_for_orders(orders)
        return OptOrderListResponse(
            items=[self._to_response(order, document_names=names) for order in orders],
        )

    async def _ensure_lead_service_opt(
        self,
        lead: Lead,
        *,
        period_code: str | None = None,
    ) -> None:
        fields = dict(lead.custom_fields or {})
        order = fields.get("order")
        if not isinstance(order, dict):
            order = {}
        next_order = {**order, "service": OPT_SERVICE_NAME}
        if period_code:
            next_order["period"] = period_code
        if next_order == order and order.get("service") == OPT_SERVICE_NAME:
            return
        fields["order"] = next_order
        lead.custom_fields = fields
        await self._leads.update_lead_fields(lead.id, custom_fields=fields)

    async def _read_chat_attachment(
        self,
        actor: User,
        *,
        lead: Lead,
        chat_id: int,
        message_id: int,
        attachment_index: int,
    ) -> tuple[bytes, str]:
        from app.modules.chats.messages import ChatMessagesService

        if lead.chat_id is None or lead.chat_id != chat_id:
            raise ValidationError(message="Файл не относится к чату этой сделки")

        messages = ChatMessagesService(self._session)
        content, _content_type, filename = await messages.get_attachment(
            actor,
            chat_id,
            message_id,
            attachment_index,
        )
        return content, filename or "application.xlsx"

    async def probe_chat_attachment(
        self,
        actor: User,
        lead_id: int,
        *,
        chat_id: int,
        message_id: int,
        attachment_index: int,
    ) -> OptAttachmentProbeResponse:
        lead = await self._get_lead_for_actor(actor, lead_id)
        content, filename = await self._read_chat_attachment(
            actor,
            lead=lead,
            chat_id=chat_id,
            message_id=message_id,
            attachment_index=attachment_index,
        )

        existing = await self._repo.get_order_by_source_attachment(message_id, attachment_index)
        if existing is not None:
            return OptAttachmentProbeResponse(
                is_application=True,
                existing_order=_existing_order_ref(existing),
            )

        if not _looks_like_spreadsheet(filename, None):
            return OptAttachmentProbeResponse(is_application=False)

        try:
            parsed = parse_application_workbook(content)
        except ValidationError:
            return OptAttachmentProbeResponse(is_application=False)

        fingerprint = compute_application_fingerprint(parsed)
        existing_fp = await self._repo.get_order_by_content_fingerprint(fingerprint)
        if existing_fp is not None:
            return OptAttachmentProbeResponse(
                is_application=True,
                buyer_inn=parsed.buyer_inn,
                line_count=len(parsed.lines),
                existing_order=_existing_order_ref(existing_fp),
            )

        return OptAttachmentProbeResponse(
            is_application=True,
            buyer_inn=parsed.buyer_inn,
            line_count=len(parsed.lines),
        )

    async def upload_from_chat_attachment(
        self,
        actor: User,
        lead_id: int,
        *,
        chat_id: int,
        message_id: int,
        attachment_index: int,
        vat_rate_percent: Decimal | float | int | None = None,
        period_code: str | None = None,
    ) -> OptOrderResponse:
        lead = await self._get_lead_for_actor(actor, lead_id)
        existing = await self._repo.get_order_by_source_attachment(message_id, attachment_index)
        if existing is not None:
            raise ValidationError(message=duplicate_order_message(existing))

        content, filename = await self._read_chat_attachment(
            actor,
            lead=lead,
            chat_id=chat_id,
            message_id=message_id,
            attachment_index=attachment_index,
        )
        return await self.upload_application(
            actor,
            lead_id,
            filename=filename,
            content=content,
            source_message_id=message_id,
            source_attachment_index=attachment_index,
            vat_rate_percent=vat_rate_percent,
            period_code=period_code,
        )

    async def upload_application(
        self,
        actor: User,
        lead_id: int,
        *,
        filename: str,
        content: bytes,
        source_message_id: int | None = None,
        source_attachment_index: int | None = None,
        vat_rate_percent: Decimal | float | int | None = None,
        period_code: str | None = None,
    ) -> OptOrderResponse:
        lead = await self._get_lead_for_actor(actor, lead_id)

        if source_message_id is not None and source_attachment_index is not None:
            existing = await self._repo.get_order_by_source_attachment(
                source_message_id,
                source_attachment_index,
            )
            if existing is not None:
                raise ValidationError(message=duplicate_order_message(existing))

        if await self._repo.lead_has_pending_submission(lead.id):
            raise ValidationError(
                message=(
                    "По сделке уже есть незавершённая заявка. "
                    "Удалите её и загрузите файл заново — повторная отправка в 1С недоступна."
                ),
            )

        parsed = parse_application_workbook(content)
        content_fingerprint = compute_application_fingerprint(parsed)
        existing_fp = await self._repo.get_order_by_content_fingerprint(content_fingerprint)
        if existing_fp is not None:
            raise ValidationError(message=duplicate_order_message(existing_fp))

        buyer_inn = parsed.buyer_inn
        buyer_kpp, buyer_name = await resolve_buyer_requisites(self._repo, buyer_inn)

        from app.modules.leads.opt.period_access import normalize_requested_period

        if period_code and str(period_code).strip():
            period_code = normalize_requested_period(str(period_code))
        else:
            period_code = read_lead_opt_period(lead.custom_fields)
        if period_code is None:
            raise ValidationError(
                message=(
                    "Для ОПТ нужно выбрать период сделки "
                    "(например 2/26 — второй квартал 2026) до загрузки заявки."
                ),
            )

        try:
            if vat_rate_percent is None:
                vat_rate = normalize_opt_vat_rate(get_settings().opt_vat_rate_percent)
            else:
                vat_rate = normalize_opt_vat_rate(vat_rate_percent)
        except ValueError as exc:
            raise ValidationError(message="НДС должен быть 20% или 22%") from exc

        order_crm_id = self._repo.new_crm_id("crm-order")
        line_payloads: list[dict[str, object]] = []
        missing_suppliers: list[str] = []
        period_blocked: list[str] = []

        for parsed_line in parsed.lines:
            unit = await self._repo.get_unit_by_inn_for_period(
                parsed_line.supplier_inn,
                period_code,
            )
            if unit is None:
                # Distinguish: exists but wrong period vs missing entirely.
                any_unit = await self._repo.get_unit_by_inn(parsed_line.supplier_inn)
                if any_unit is None:
                    missing_suppliers.append(parsed_line.supplier_inn)
                else:
                    period_blocked.append(parsed_line.supplier_inn)
                supplier_kpp = None
                supplier_name = None
            else:
                unit = await ensure_unit_requisites(self._repo, unit)
                supplier_kpp = unit.kpp
                supplier_name = unit.name

            total, vat, wo_vat = split_vat_included(parsed_line.amount, rate_percent=vat_rate)
            line_payloads.append(
                {
                    "crm_id": self._repo.new_crm_id("crm-line"),
                    "supplier_inn": parsed_line.supplier_inn,
                    "supplier_kpp": supplier_kpp,
                    "supplier_name": supplier_name,
                    "document_date": parsed_line.document_date,
                    "amount": float(total),
                    "vat_amount": float(vat),
                    "amount_without_vat": float(wo_vat),
                },
            )

        if missing_suppliers:
            raise ValidationError(
                message=(
                    "Не найдены лавки (opt_units) для ИНН: "
                    + ", ".join(sorted(set(missing_suppliers)))
                ),
            )
        if period_blocked:
            raise ValidationError(
                message=(
                    f"Лавки не доступны для периода {period_code}: "
                    + ", ".join(sorted(set(period_blocked)))
                ),
            )

        order = await self._repo.create_order(
            lead_id=lead.id,
            crm_id=order_crm_id,
            buyer_inn=buyer_inn,
            buyer_kpp=buyer_kpp,
            buyer_name=buyer_name,
            source_filename=filename,
            created_by=actor.id,
            lines=line_payloads,
            source_message_id=source_message_id,
            source_attachment_index=source_attachment_index,
            content_fingerprint=content_fingerprint,
            vat_rate_percent=float(vat_rate),
            period_code=period_code,
        )
        await self._ensure_lead_service_opt(lead, period_code=period_code)
        await self._session.commit()
        await enqueue_opt_submit(order.id)
        refreshed = await self._repo.get_order(order.id)
        assert refreshed is not None
        return self._to_response(refreshed)

    @staticmethod
    def _mole_party(*, inn: str, kpp: str | None, name: str) -> dict[str, str]:
        # Mole always reads .КПП; missing key fails. Empty string is OK for individuals.
        return {"ИНН": inn, "КПП": (kpp or "").strip(), "Наименование": name}

    @staticmethod
    def _build_mole_payload(order: LeadOptOrder) -> dict[str, Any]:
        if not order.buyer_name:
            raise ValidationError(
                message=(
                    "Для отправки в 1С нужно наименование покупателя "
                    f"(ИНН {order.buyer_inn})"
                ),
            )

        registry: list[dict[str, Any]] = []
        for line in sorted(order.lines, key=lambda row: row.line_no):
            if not line.supplier_name:
                raise ValidationError(
                    message=f"Для лавки {line.supplier_inn} не заполнено наименование",
                )
            doc_date = line.document_date
            if isinstance(doc_date, date):
                date_text = doc_date.isoformat()
            else:
                date_text = str(doc_date)
            registry.append(
                {
                    "CRMid": line.crm_id,
                    "Поставщик": OptOrderService._mole_party(
                        inn=line.supplier_inn,
                        kpp=line.supplier_kpp,
                        name=line.supplier_name,
                    ),
                    "ДатаДокумента": date_text,
                    "Сумма": float(line.amount),
                    "СуммаНДС": float(line.vat_amount),
                    "СуммаБезНДС": float(line.amount_without_vat),
                },
            )

        return {
            "CRMid": order.crm_id,
            "Покупатель": OptOrderService._mole_party(
                inn=order.buyer_inn,
                kpp=order.buyer_kpp,
                name=order.buyer_name,
            ),
            "Реестр": registry,
        }

    @staticmethod
    def _extract_line_numbers(response: dict[str, Any]) -> dict[str, str]:
        mapping: dict[str, str] = {}
        registry = response.get("Реестр") or response.get("Registry") or []
        if not isinstance(registry, list):
            return mapping
        for item in registry:
            if not isinstance(item, dict):
                continue
            crm_id = str(item.get("CRMid") or item.get("ID") or "").strip()
            doc_no = str(item.get("НомерДокумента") or item.get("DocumentNumber") or "").strip()
            if crm_id and doc_no:
                mapping[crm_id] = doc_no
        return mapping

    async def _publish_status(self, order: LeadOptOrder) -> None:
        await publish(
            "opt.order.updated",
            {
                "lead_id": order.lead_id,
                "order_id": order.id,
                "order_no": order.order_no,
                "status": order.status,
            },
        )

    async def _execute_submit(self, order: LeadOptOrder, *, actor_id: int | None) -> None:
        if order.status == "submitted":
            return
        if not order.lines:
            raise ValidationError(message="В заявке нет строк реестра")

        await self._ensure_order_requisites(order)

        payload = self._build_mole_payload(order)
        await self._repo.mark_submitting(order)
        await self._session.flush()
        await self._publish_status(order)

        try:
            response = await post_opt_order(payload)
            line_numbers = self._extract_line_numbers(response)
            if len(line_numbers) != len(order.lines):
                raise MoleApiError(
                    message="1С вернула неполный реестр номеров документов",
                    details={"expected": len(order.lines), "got": len(line_numbers)},
                )
            await self._repo.mark_submitted(
                order,
                actor_id=actor_id,
                request_payload=payload,
                response_payload=response,
                line_numbers=line_numbers,
            )
        except MoleApiError as exc:
            details = exc.details or {}
            body = details.get("body")
            response_payload: dict[str, object] | None
            if isinstance(body, dict):
                response_payload = body
            elif details.get("text") is not None:
                response_payload = {
                    "text": details.get("text"),
                    "http_status": details.get("http_status"),
                }
            else:
                response_payload = None
            await self._repo.mark_failed(
                order,
                actor_id=actor_id,
                request_payload=payload,
                response_payload=response_payload,
                error_message=exc.message,
            )
            await self._publish_status(order)
            raise

        await self._publish_status(order)

    async def _ensure_order_requisites(self, order: LeadOptOrder) -> None:
        if not order.buyer_name or not order.buyer_kpp:
            kpp, name = await resolve_buyer_requisites(self._repo, order.buyer_inn)
            if name and not order.buyer_name:
                order.buyer_name = name
            if kpp and not order.buyer_kpp:
                order.buyer_kpp = kpp
        for line in order.lines:
            if line.supplier_kpp and line.supplier_name:
                continue
            unit = await self._repo.get_unit_by_inn(line.supplier_inn)
            if unit is None:
                continue
            unit = await ensure_unit_requisites(self._repo, unit)
            if unit.name and not line.supplier_name:
                line.supplier_name = unit.name
            if unit.kpp and not line.supplier_kpp:
                line.supplier_kpp = unit.kpp

    async def _hydrate_registry_requisites(self, order: LeadOptOrder) -> None:
        if not order.buyer_kpp or not order.buyer_name:
            kpp, name = await resolve_buyer_requisites(self._repo, order.buyer_inn)
            if name and not order.buyer_name:
                order.buyer_name = name
            if kpp and not order.buyer_kpp:
                order.buyer_kpp = kpp

        for line in order.lines:
            if line.supplier_kpp and line.supplier_name:
                continue
            unit = await self._repo.get_unit_by_inn(line.supplier_inn)
            if unit is None:
                continue
            unit = await ensure_unit_requisites(self._repo, unit)
            if unit.name and not line.supplier_name:
                line.supplier_name = unit.name
            if unit.kpp and not line.supplier_kpp:
                line.supplier_kpp = unit.kpp

    async def submit_order_worker(self, order_id: int) -> None:
        order = await self._repo.get_order(order_id)
        if order is None:
            return
        if order.status == "submitted":
            return
        if order.status not in {"queued", "failed", "submitting"}:
            return
        try:
            await self._execute_submit(order, actor_id=order.created_by)
        except MoleApiError:
            return
        except ValidationError as exc:
            await self._repo.mark_failed(
                order,
                actor_id=order.created_by,
                request_payload=None,
                error_message=exc.message,
            )
            await self._publish_status(order)

    async def submit_order(self, actor: User, lead_id: int, order_id: int) -> OptOrderResponse:
        order = await self._get_order_for_actor(actor, lead_id, order_id)
        if order.status == "submitted":
            raise ValidationError(message="Заявка уже отправлена в 1С")
        await self._execute_submit(order, actor_id=actor.id)
        await self._session.commit()
        refreshed = await self._repo.get_order(order.id)
        assert refreshed is not None
        return self._to_response(refreshed)

    async def update_order_period(
        self,
        actor: User,
        order_id: int,
        period_code: str,
    ) -> tuple[int, int, str]:
        """Set/change period for an order visible in actor lead scope.

        Any user with lead access may change period; lavkas must be allowed
        for the target period (opt_unit_period_availability).
        """
        from app.modules.leads.opt.period_access import (
            assert_supplier_inns_allowed_for_period,
            normalize_requested_period,
        )

        order = await self._repo.get_order(order_id)
        if order is None:
            raise NotFound(message="OPT order not found")
        await self._get_lead_for_actor(actor, order.lead_id)
        new_code = normalize_requested_period(period_code)
        current = normalize_period_code(getattr(order, "period_code", None) or "")
        if current == new_code:
            return order.id, order.lead_id, new_code
        await assert_supplier_inns_allowed_for_period(
            self._session,
            period_code=new_code,
            supplier_inns=[line.supplier_inn for line in order.lines],
        )
        order.period_code = new_code
        await self._session.flush()
        return order.id, order.lead_id, new_code

    async def delete_order(self, actor: User, lead_id: int, order_id: int) -> None:
        order = await self._get_order_for_actor(actor, lead_id, order_id)
        if order.deleted_at is not None:
            raise NotFound(message="OPT order not found")

        lead_id_value = order.lead_id
        order_no = order.order_no
        snapshot = self._order_delete_snapshot(order)

        try:
            await dequeue_opt_submit(order.id)
        except Exception:
            logger.warning("opt_submit_dequeue_failed", order_id=order.id, exc_info=True)

        await self._repo.soft_delete_order(
            order,
            actor_id=int(actor.id),
            snapshot=snapshot,
        )
        await self._repo.renumber_orders_for_lead(lead_id_value)
        await self._session.commit()
        await publish(
            "opt.order.deleted",
            {
                "lead_id": lead_id_value,
                "order_id": order_id,
                "order_no": order_no,
                "soft": True,
                "status": order.status,
                "actor_id": int(actor.id),
            },
        )

    async def restore_order(self, actor: User, lead_id: int, order_id: int) -> OptOrderResponse:
        if not is_admin(actor.role):
            raise PermissionDenied(message="Восстановление заявок доступно только администраторам")
        order = await self._repo.get_order(order_id)
        if order is None or order.lead_id != lead_id or order.deleted_at is None:
            raise NotFound(message="Удалённая OPT-заявка не найдена")
        await self._get_lead_for_actor(actor, lead_id)
        await self._repo.restore_order(order)
        await self._repo.renumber_orders_for_lead(lead_id)
        await self._session.commit()
        restored = await self._repo.get_order(order_id)
        assert restored is not None
        await publish(
            "opt.order.restored",
            {"lead_id": lead_id, "order_id": order_id, "actor_id": int(actor.id)},
        )
        return self._to_response(restored)

    def _order_delete_snapshot(self, order: LeadOptOrder) -> dict:
        return {
            "id": order.id,
            "lead_id": order.lead_id,
            "crm_id": order.crm_id,
            "order_no": order.order_no,
            "buyer_inn": order.buyer_inn,
            "buyer_kpp": order.buyer_kpp,
            "buyer_name": order.buyer_name,
            "status": order.status,
            "period_code": order.period_code,
            "total_volume": float(order.total_volume or 0),
            "commission_due": float(order.commission_due or 0),
            "source_filename": order.source_filename,
            "submission_error": order.submission_error,
            "lines": [
                {
                    "crm_id": line.crm_id,
                    "supplier_inn": line.supplier_inn,
                    "document_date": str(line.document_date),
                    "amount": float(line.amount),
                }
                for line in order.lines
            ],
        }

    async def send_registry_to_client(
        self,
        actor: User,
        lead_id: int,
        order_id: int,
    ) -> dict[str, int]:
        from app.modules.chats.messages import ChatMessagesService
        from app.modules.chats.schemas import AttachmentInput, OutboundMessageRequest
        from app.modules.files.service import FilesService

        order = await self._get_order_for_actor(actor, lead_id, order_id)
        if order.status != "submitted":
            raise ValidationError(message="Реестр можно отправить после успешной обработки в 1С")
        lead = await self._get_lead_for_actor(actor, lead_id)
        if lead.chat_id is None:
            raise ValidationError(message="У сделки нет чата — отправка клиенту недоступна")

        await self._hydrate_registry_requisites(order)
        content, filename = self._registry_bytes(order)
        files = FilesService(self._session)
        uploaded = await files.create_upload(
            uploaded_by=actor.id,
            data=content,
            original_name=filename,
            mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        text = f"Реестр по заявке №{order.order_no} сделки №{lead_id}."
        messages = ChatMessagesService(self._session)
        message, _, _ = await messages.send_outbound(
            actor,
            lead.chat_id,
            OutboundMessageRequest(
                text=text,
                attachments=[
                    AttachmentInput(
                        file_id=uploaded.id,
                        name=filename,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        size=len(content),
                    ),
                ],
            ),
        )
        await self._session.commit()
        return {"message_id": message.id, "chat_id": lead.chat_id}

    def _registry_bytes(self, order: LeadOptOrder) -> tuple[bytes, str]:
        content = build_registry_workbook(order, sorted(order.lines, key=lambda row: row.line_no))
        buyer_slug = (order.buyer_name or order.buyer_inn).replace("/", "-")[:40]
        filename = f"РЕЕСТР СФ ЗАКАЗ {buyer_slug} заявка-{order.order_no}.xlsx"
        return content, filename

    async def export_registry(
        self,
        actor: User,
        lead_id: int,
        order_id: int,
    ) -> tuple[bytes, str]:
        order = await self._get_order_for_actor(actor, lead_id, order_id)
        if order.status != "submitted":
            raise ValidationError(message="Реестр доступен после успешной отправки в 1С")
        await self._hydrate_registry_requisites(order)
        await self._session.commit()
        return self._registry_bytes(order)

    async def sync_orders_with_1c(self, actor: User, period_code: str) -> OptSync1cResponse:
        if not is_admin(actor.role):
            raise PermissionDenied(message="Сверка с 1С доступна только администраторам")

        normalized = normalize_period_code(period_code)
        if normalized is None:
            raise ValidationError(message="Некорректный период (ожидается формат Q/YY, например 2/26)")
        period_iso = period_code_to_mole_iso(normalized)
        if period_iso is None:
            raise ValidationError(message="Некорректный период")

        local_orders = await self._repo.list_submitted_by_period(normalized)
        local_payloads: dict[str, dict[str, Any]] = {}
        local_by_crm: dict[str, LeadOptOrder] = {}
        for order in local_orders:
            await self._ensure_order_requisites(order)
            try:
                payload = self._build_mole_payload(order)
            except ValidationError as exc:
                logger.warning(
                    "opt_sync_skip_local_order",
                    crm_id=order.crm_id,
                    error=exc.message,
                )
                continue
            local_payloads[order.crm_id] = payload
            local_by_crm[order.crm_id] = order

        report = OptSync1cResponse(period_code=normalized, period_iso=period_iso)

        def _mole_missing(exc: MoleApiError) -> bool:
            status = (exc.details or {}).get("http_status")
            if status == 404:
                return True
            msg = (exc.message or "").lower()
            return any(
                token in msg
                for token in ("не найден", "not found", "не существует", "отсутствует")
            )

        async with mole_session():
            mole_orders = await mole_filter_orders(period_iso=period_iso)
            planned = plan_sync_actions(
                local_crm_ids=set(local_payloads),
                local_payloads=local_payloads,
                mole_orders=mole_orders,
            )
            # HTTP only in parallel (no DB). Then apply DB writes sequentially.
            sem = asyncio.Semaphore(5)

            async def _http_one(
                kind: str,
                crm_id: str,
            ) -> tuple[str, str, dict[str, Any] | None, str | None]:
                async with sem:
                    try:
                        if kind == "delete_extra":
                            await mole_delete_order(crm_id)
                            return kind, crm_id, None, None

                        payload = local_payloads[crm_id]
                        effective = kind

                        if kind in {"check", "restore"}:
                            remote: dict[str, Any] | None = None
                            try:
                                remote = await mole_get_order(crm_id)
                            except MoleApiError as exc:
                                if kind == "check" or not _mole_missing(exc):
                                    # check: order listed in filter must be GET-able
                                    # restore: non-404 errors must not fall through to POST
                                    raise
                                remote = None

                            if remote is not None and not mole_is_deleted(remote):
                                if registries_match(payload, remote):
                                    return "unchanged", crm_id, None, None
                                effective = "update"
                            else:
                                effective = "restore"

                        if effective == "update":
                            response = await mole_put_order(crm_id, payload)
                            return "update", crm_id, response, None

                        # restore: prefer PUT (same CRMid). POST only if order truly missing.
                        try:
                            response = await mole_put_order(crm_id, payload)
                            return "restore", crm_id, response, None
                        except MoleApiError as exc:
                            if not _mole_missing(exc):
                                raise
                            response = await post_opt_order(payload)
                            return "restore", crm_id, response, None
                    except MoleApiError as exc:
                        return kind, crm_id, None, exc.message
                    except Exception as exc:  # noqa: BLE001
                        logger.exception("opt_sync_action_failed", crm_id=crm_id, action=kind)
                        return kind, crm_id, None, str(exc)[:500]

            http_results = await asyncio.gather(
                *[_http_one(kind, crm_id) for kind, crm_id in planned if kind != "unchanged"],
            )

        for kind, crm_id, response, error in http_results:
            if kind == "unchanged" and error is None:
                report.unchanged += 1
                continue
            if error:
                report.errors.append(
                    OptSync1cActionItem(action=kind, crm_id=crm_id, detail=error),
                )
                continue
            try:
                if kind == "delete_extra":
                    report.deleted_extra += 1
                    report.actions.append(
                        OptSync1cActionItem(
                            action=kind,
                            crm_id=crm_id,
                            detail="Удалена лишняя заявка в 1С",
                        ),
                    )
                    continue
                order = local_by_crm[crm_id]
                payload = local_payloads[crm_id]
                assert response is not None
                await self._apply_mole_submit_success(
                    order,
                    actor_id=actor.id,
                    payload=payload,
                    response=response,
                )
                if kind == "update":
                    report.updated += 1
                    detail = "Обновлена в 1С по данным CRM"
                else:
                    report.restored += 1
                    detail = "Восстановлена в 1С"
                report.actions.append(
                    OptSync1cActionItem(action=kind, crm_id=crm_id, detail=detail),
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("opt_sync_db_apply_failed", crm_id=crm_id, action=kind)
                report.errors.append(
                    OptSync1cActionItem(action=kind, crm_id=crm_id, detail=str(exc)[:500]),
                )

        # Count filter-level unchanged from plan (not sent to HTTP).
        report.unchanged += sum(1 for kind, _ in planned if kind == "unchanged")

        await self._session.flush()
        return report

    async def _apply_mole_submit_success(
        self,
        order: LeadOptOrder,
        *,
        actor_id: int,
        payload: dict[str, Any],
        response: dict[str, Any],
    ) -> None:
        line_numbers = self._extract_line_numbers(response)
        await self._repo.mark_submitted(
            order,
            actor_id=actor_id,
            request_payload=payload,
            response_payload=response,
            line_numbers=line_numbers,
        )
        await self._publish_status(order)
