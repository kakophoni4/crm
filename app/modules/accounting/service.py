from __future__ import annotations

import base64
import binascii
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.accounting.repository import AccountingRepository
from app.modules.accounting.schemas import (
    AccountingAssignmentItem,
    AccountingAssignmentListResponse,
    AccountingOrderLineItem,
    AccountingOrderLineListResponse,
    AccountingRequirementIngestRequest,
    AccountingRequirementIngestResponse,
    AccountingRequirementListResponse,
    AccountingRequirementResponse,
    AccountingSupplierResponse,
    AccountingUnitListResponse,
    AccountingUnitResponse,
)
from app.modules.db.models.enums import UserRole
from app.modules.db.models.opt_requirement import OptRequirement
from app.modules.db.models.user import User
from app.modules.files.service import FilesService
from app.modules.leads.opt.registry_export import build_registry_workbook
from app.modules.rbac.permissions import Permission
from app.modules.rbac.role_map import has_permission
from app.shared.exceptions import NotFound, PermissionDenied, ValidationError


class AccountingService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = AccountingRepository(session)

    def _is_chief(self, actor: User) -> bool:
        role = actor.role if isinstance(actor.role, UserRole) else UserRole(str(actor.role))
        if role == UserRole.ADMIN:
            return True
        return has_permission(role, Permission.ACCOUNTING_MANAGE)

    async def _visible_supplier_inns(self, actor: User) -> set[str] | None:
        if self._is_chief(actor):
            return None
        unit_ids = await self._repo.list_assigned_unit_ids(actor.id)
        if not unit_ids:
            return set()
        units = await self._repo.get_units_by_ids(unit_ids)
        return {unit.inn for unit in units.values()}

    async def list_units(self, actor: User) -> AccountingUnitListResponse:
        is_chief = self._is_chief(actor)
        all_units = await self._repo.list_active_units()
        if is_chief:
            visible = all_units
        else:
            unit_ids = set(await self._repo.list_assigned_unit_ids(actor.id))
            visible = [unit for unit in all_units if unit.id in unit_ids]
        return AccountingUnitListResponse(
            is_chief=is_chief,
            items=[
                AccountingUnitResponse(
                    id=unit.id,
                    inn=unit.inn,
                    kpp=unit.kpp,
                    name=unit.name,
                    category_code=unit.category_code,
                    is_active=unit.is_active,
                )
                for unit in visible
            ],
        )

    async def list_order_lines(
        self,
        actor: User,
        *,
        supplier_inn: str | None,
        status: str | None,
        manager_user_id: int | None,
        date_from: date | None,
        date_to: date | None,
        q: str | None,
        limit: int,
        offset: int,
    ) -> AccountingOrderLineListResponse:
        supplier_inns = await self._visible_supplier_inns(actor)
        filters = {
            "supplier_inns": supplier_inns,
            "supplier_inn": supplier_inn,
            "status": status,
            "manager_user_id": manager_user_id,
            "date_from": date_from,
            "date_to": date_to,
            "q": q,
        }
        total = await self._repo.count_order_lines(**filters)
        rows = await self._repo.list_order_lines(limit=limit, offset=offset, **filters)
        unit_cache: dict[str, str | None] = {}
        items: list[AccountingOrderLineItem] = []
        for line, order, _lead, contact_name, manager_id, manager_name in rows:
            category_code = unit_cache.get(line.supplier_inn)
            if line.supplier_inn not in unit_cache:
                unit = await self._repo.get_unit_by_inn(line.supplier_inn)
                category_code = unit.category_code if unit else None
                unit_cache[line.supplier_inn] = category_code
            items.append(
                AccountingOrderLineItem(
                    line_id=line.id,
                    line_no=line.line_no,
                    order_id=order.id,
                    lead_id=order.lead_id,
                    order_no=order.order_no,
                    crm_id=order.crm_id,
                    status=order.status,
                    payment_status=order.payment_status or "unpaid",
                    supplier=AccountingSupplierResponse(
                        inn=line.supplier_inn,
                        kpp=line.supplier_kpp,
                        name=line.supplier_name,
                        category_code=category_code,
                    ),
                    buyer_inn=order.buyer_inn,
                    buyer_name=order.buyer_name,
                    document_date=line.document_date,
                    amount=Decimal(str(line.amount)),
                    manager_user_id=manager_id,
                    manager_full_name=manager_name,
                    contact_name=contact_name,
                    source_filename=order.source_filename,
                    submitted_at=order.submitted_at,
                    created_at=order.created_at,
                ),
            )
        return AccountingOrderLineListResponse(
            items=items,
            total=total,
            limit=limit,
            offset=offset,
        )

    async def export_registry(self, actor: User, order_id: int) -> tuple[bytes, str]:
        supplier_inns = await self._visible_supplier_inns(actor)
        if not await self._repo.order_visible_for_supplier_inns(order_id, supplier_inns):
            raise NotFound(message="Заявка не найдена")
        order = await self._repo.get_order_for_registry(order_id)
        if order is None:
            raise NotFound(message="Заявка не найдена")
        content = build_registry_workbook(order, sorted(order.lines, key=lambda row: row.line_no))
        filename = order.source_filename or f"registry_{order.crm_id}.xlsx"
        if not filename.lower().endswith(".xlsx"):
            filename = f"{filename}.xlsx"
        return content, filename

    async def list_requirements(
        self,
        actor: User,
        *,
        supplier_inn: str | None,
        status: str | None,
        q: str | None,
        limit: int,
        offset: int,
    ) -> AccountingRequirementListResponse:
        supplier_inns = await self._visible_supplier_inns(actor)
        filters = {
            "supplier_inns": supplier_inns,
            "supplier_inn": supplier_inn,
            "status": status,
            "q": q,
        }
        total = await self._repo.count_requirements(**filters)
        rows = await self._repo.list_requirements(limit=limit, offset=offset, **filters)
        return AccountingRequirementListResponse(
            items=[self._requirement_to_response(row) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def get_requirement_pdf(self, actor: User, requirement_id: int) -> tuple[bytes, str, str]:
        supplier_inns = await self._visible_supplier_inns(actor)
        row = await self._repo.get_requirement(requirement_id)
        if row is None:
            raise NotFound(message="Требование не найдено")
        if supplier_inns is not None and row.supplier_inn not in supplier_inns:
            raise NotFound(message="Требование не найдено")
        if row.pdf_file_id is None:
            raise NotFound(message="PDF не прикреплён")
        files = FilesService(self._session)
        data, content_type, filename = await files.get_bytes(row.pdf_file_id)
        return data, content_type, filename

    async def ingest_requirement(
        self,
        body: AccountingRequirementIngestRequest,
        *,
        pdf_bytes: bytes | None,
        pdf_filename: str | None,
    ) -> AccountingRequirementIngestResponse:
        existing = await self._repo.get_requirement_by_external_id(body.external_id.strip())
        if existing is not None:
            return AccountingRequirementIngestResponse(
                id=existing.id,
                external_id=existing.external_id,
                created=False,
            )

        unit = await self._repo.get_unit_by_inn(body.supplier_inn.strip())
        supplier_kpp = body.supplier_kpp or (unit.kpp if unit else None)
        supplier_name = body.supplier_name or (unit.name if unit else None)

        file_id: int | None = None
        raw_pdf = pdf_bytes
        if raw_pdf is None and body.pdf_base64:
            try:
                raw_pdf = base64.b64decode(body.pdf_base64, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise ValidationError(message="Некорректный pdf_base64") from exc
        if raw_pdf:
            if not raw_pdf.startswith(b"%PDF"):
                raise ValidationError(message="Файл должен быть PDF")
            files = FilesService(self._session)
            uploaded = await files.create_upload(
                uploaded_by=None,
                data=raw_pdf,
                original_name=pdf_filename or body.pdf_filename or "requirement.pdf",
                mime_type="application/pdf",
            )
            file_id = uploaded.id

        received_at = body.received_at or datetime.now(UTC)
        row = OptRequirement(
            external_id=body.external_id.strip(),
            supplier_inn=body.supplier_inn.strip(),
            supplier_kpp=supplier_kpp,
            supplier_name=supplier_name,
            title=body.title.strip(),
            description=body.description.strip() if body.description else None,
            status=body.status or "new",
            pdf_file_id=file_id,
            metadata_json=body.metadata or {},
            received_at=received_at,
        )
        created = await self._repo.add_requirement(row)
        await self._session.commit()
        return AccountingRequirementIngestResponse(
            id=created.id,
            external_id=created.external_id,
            created=True,
        )

    async def list_assignments(self, actor: User) -> AccountingAssignmentListResponse:
        if not self._is_chief(actor):
            raise PermissionDenied()
        users = await self._repo.list_accountant_users()
        user_ids = [user.id for user in users]
        assignments = await self._repo.list_assignments_for_users(user_ids)
        by_user: dict[int, list[int]] = {uid: [] for uid in user_ids}
        for row in assignments:
            by_user.setdefault(row.user_id, []).append(row.unit_id)
        return AccountingAssignmentListResponse(
            items=[
                AccountingAssignmentItem(
                    user_id=user.id,
                    user_full_name=user.full_name,
                    unit_ids=sorted(by_user.get(user.id, [])),
                )
                for user in users
            ],
        )

    async def update_assignments(
        self,
        actor: User,
        user_id: int,
        unit_ids: list[int],
    ) -> AccountingAssignmentItem:
        if not self._is_chief(actor):
            raise PermissionDenied()
        users = await self._repo.list_accountant_users()
        target = next((user for user in users if user.id == user_id), None)
        if target is None:
            raise NotFound(message="Бухгалтер не найден")
        unique_ids = sorted({int(uid) for uid in unit_ids if uid > 0})
        units = await self._repo.get_units_by_ids(unique_ids)
        missing = [uid for uid in unique_ids if uid not in units]
        if missing:
            raise ValidationError(
                message="Неизвестные лавки",
                details={"unit_ids": missing},
            )
        await self._repo.replace_user_assignments(user_id, unique_ids, assigned_by=actor.id)
        await self._session.commit()
        return AccountingAssignmentItem(
            user_id=target.id,
            user_full_name=target.full_name,
            unit_ids=unique_ids,
        )

    def _requirement_to_response(self, row: OptRequirement) -> AccountingRequirementResponse:
        pdf_name = row.pdf_file.original_name if row.pdf_file is not None else None
        return AccountingRequirementResponse(
            id=row.id,
            external_id=row.external_id,
            supplier=AccountingSupplierResponse(
                inn=row.supplier_inn,
                kpp=row.supplier_kpp,
                name=row.supplier_name,
            ),
            title=row.title,
            description=row.description,
            status=row.status,
            has_pdf=row.pdf_file_id is not None,
            pdf_filename=pdf_name,
            metadata=row.metadata_json or {},
            received_at=row.received_at,
            created_at=row.created_at,
        )
