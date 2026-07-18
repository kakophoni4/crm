from __future__ import annotations

import base64
import binascii
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.accounting.repository import AccountingRepository
from app.modules.accounting.schemas import (
    AccountingAccountantOption,
    AccountingAssignmentItem,
    AccountingAssignmentListResponse,
    AccountingOrderLineBrief,
    AccountingOrderLineItem,
    AccountingOrderLineListResponse,
    AccountingRequirementIngestRequest,
    AccountingRequirementIngestResponse,
    AccountingRequirementListResponse,
    AccountingRequirementResponse,
    AccountingSupplierResponse,
    AccountingUnitCategoriesResponse,
    AccountingUnitCategoryOption,
    AccountingUnitCreateRequest,
    AccountingUnitListResponse,
    AccountingUnitOrderGroup,
    AccountingUnitOrderItem,
    AccountingUnitOrdersResponse,
    AccountingUnitOwnerListResponse,
    AccountingUnitOwnerRow,
    AccountingUnitPatchRequest,
    AccountingUnitResponse,
)
from app.modules.db.models.enums import UserRole
from app.modules.db.models.opt_requirement import OptRequirement
from app.modules.db.models.opt_unit import OptUnit
from app.modules.db.models.user import User
from app.modules.files.service import FilesService
from app.modules.leads.opt.registry_export import build_registry_workbook
from app.modules.rbac.permissions import Permission
from app.modules.rbac.role_map import has_permission
from app.shared.exceptions import NotFound, PermissionDenied, ValidationError

_ACCOUNTING_ORDER_STATUS = "submitted"


class AccountingService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = AccountingRepository(session)

    def _is_chief(self, actor: User) -> bool:
        role = actor.role if isinstance(actor.role, UserRole) else UserRole(str(actor.role))
        if role == UserRole.ADMIN:
            return True
        return has_permission(role, Permission.ACCOUNTING_MANAGE)

    async def _visible_supplier_inns(
        self,
        actor: User,
        *,
        active_only: bool = True,
    ) -> set[str] | None:
        """INNs in actor scope. None = chief (all).

        active_only=True  → продающие лавки (заявки / сдача)
        active_only=False → все назначенные, включая лавки только для требований
        """
        if self._is_chief(actor):
            return None
        unit_ids = await self._repo.list_assigned_unit_ids(actor.id)
        if not unit_ids:
            return set()
        units = await self._repo.get_units_by_ids(unit_ids, active_only=active_only)
        return {unit.inn for unit in units.values()}

    def _normalize_period_codes(self, period_codes: list[str]) -> list[str]:
        from app.modules.leads.opt.periods import list_opt_period_codes, normalize_period_code

        allowed = set(list_opt_period_codes())
        cleaned: list[str] = []
        seen: set[str] = set()
        invalid: list[str] = []
        for raw in period_codes:
            code = normalize_period_code(raw)
            if code is None or code not in allowed:
                invalid.append(str(raw))
                continue
            if code in seen:
                continue
            seen.add(code)
            cleaned.append(code)
        if invalid:
            raise ValidationError(
                message="Некорректные периоды",
                details={"period_codes": invalid, "allowed": sorted(allowed)},
            )
        return cleaned

    def _to_unit_response(self, unit: OptUnit, period_codes: list[str] | None = None) -> AccountingUnitResponse:
        return AccountingUnitResponse(
            id=unit.id,
            inn=unit.inn,
            kpp=unit.kpp,
            name=unit.name,
            category_code=unit.category_code,
            commission_rate_percent=unit.commission_rate_percent,
            is_active=unit.is_active,
            period_codes=list(period_codes or []),
        )

    async def list_units(self, actor: User) -> AccountingUnitListResponse:
        is_chief = self._is_chief(actor)
        all_units = await self._repo.list_active_units()
        if is_chief:
            visible = all_units
        else:
            unit_ids = set(await self._repo.list_assigned_unit_ids(actor.id))
            visible = [unit for unit in all_units if unit.id in unit_ids]
        periods_by_inn = await self._repo.list_period_codes_by_inns([unit.inn for unit in visible])
        return AccountingUnitListResponse(
            is_chief=is_chief,
            items=[
                self._to_unit_response(unit, periods_by_inn.get(unit.inn, []))
                for unit in visible
            ],
        )

    def list_categories(self) -> AccountingUnitCategoriesResponse:
        from app.modules.leads.opt.tariffs import (
            ALL_CATEGORY_CODES,
            CATEGORY_BASE_RATE_PERCENT,
            CATEGORY_LABELS,
        )

        return AccountingUnitCategoriesResponse(
            items=[
                AccountingUnitCategoryOption(
                    code=code,
                    label=CATEGORY_LABELS.get(code, code),
                    base_rate_percent=CATEGORY_BASE_RATE_PERCENT.get(code),
                )
                for code in ALL_CATEGORY_CODES
            ],
        )

    async def create_unit(
        self,
        actor: User,
        body: AccountingUnitCreateRequest,
    ) -> AccountingUnitResponse:
        if not self._is_chief(actor):
            raise PermissionDenied()

        from app.modules.leads.opt.tariffs import ALL_CATEGORY_CODES

        category_code = body.category_code.strip().upper()
        if category_code not in ALL_CATEGORY_CODES:
            raise ValidationError(
                message="Неизвестный тип компании",
                details={"category_code": category_code},
            )

        inn = body.inn.strip()
        existing = await self._repo.get_unit_by_inn_any(inn)
        if existing is not None:
            raise ValidationError(message="Лавка с таким ИНН уже существует")

        period_codes = self._normalize_period_codes(body.period_codes)
        if not period_codes:
            raise ValidationError(message="Укажите хотя бы один разрешённый период")

        unit = OptUnit(
            inn=inn,
            kpp=body.kpp,
            name=body.name.strip(),
            category_code=category_code,
            commission_rate_percent=body.commission_rate_percent,
            is_active=True,
        )
        created = await self._repo.add_unit(unit)
        saved_periods = await self._repo.replace_unit_periods(
            unit_id=created.id,
            inn=created.inn,
            period_codes=period_codes,
        )
        await self._session.commit()
        return self._to_unit_response(created, saved_periods)

    async def update_unit(
        self,
        actor: User,
        unit_id: int,
        body: AccountingUnitPatchRequest,
    ) -> AccountingUnitResponse:
        if not self._is_chief(actor):
            raise PermissionDenied()

        units = await self._repo.get_units_by_ids([unit_id], active_only=False)
        unit = units.get(unit_id)
        if unit is None:
            raise NotFound(message="Лавка не найдена")

        if (
            body.commission_rate_percent is None
            and body.name is None
            and body.category_code is None
            and body.period_codes is None
            and body.is_active is None
        ):
            raise ValidationError(message="Нет полей для обновления")

        if body.commission_rate_percent is not None:
            unit.commission_rate_percent = body.commission_rate_percent
        if body.name is not None:
            unit.name = body.name
        if body.is_active is not None:
            unit.is_active = body.is_active
        if body.category_code is not None:
            from app.modules.leads.opt.tariffs import ALL_CATEGORY_CODES

            category_code = body.category_code.strip().upper()
            if category_code not in ALL_CATEGORY_CODES:
                raise ValidationError(
                    message="Неизвестный тип компании",
                    details={"category_code": category_code},
                )
            unit.category_code = category_code

        period_codes: list[str] | None = None
        if body.period_codes is not None:
            period_codes = await self._repo.replace_unit_periods(
                unit_id=unit.id,
                inn=unit.inn,
                period_codes=self._normalize_period_codes(body.period_codes),
            )

        await self._session.flush()
        await self._session.commit()
        await self._session.refresh(unit)
        if period_codes is None:
            periods_by_inn = await self._repo.list_period_codes_by_inns([unit.inn])
            period_codes = periods_by_inn.get(unit.inn, [])
        return self._to_unit_response(unit, period_codes)

    async def list_orders_by_units(
        self,
        actor: User,
        *,
        supplier_inn: str | None,
        manager_user_id: int | None,
        date_from: date | None,
        date_to: date | None,
        q: str | None,
        limit: int,
        offset: int,
    ) -> AccountingUnitOrdersResponse:
        supplier_inns = await self._visible_supplier_inns(actor)
        filters = {
            "supplier_inns": supplier_inns,
            "supplier_inn": supplier_inn,
            "status": _ACCOUNTING_ORDER_STATUS,
            "manager_user_id": manager_user_id,
            "date_from": date_from,
            "date_to": date_to,
            "q": q,
        }
        rows = await self._repo.list_order_lines_all(**filters)
        unit_cache: dict[str, OptUnit | None] = {}
        groups: dict[str, dict[int, AccountingUnitOrderItem]] = {}
        unit_meta: dict[str, AccountingUnitResponse] = {}

        for line, order, _lead, contact_name, manager_id, manager_name in rows:
            inn = line.supplier_inn
            if inn not in unit_cache:
                unit_cache[inn] = await self._repo.get_unit_by_inn(inn)
            unit_row = unit_cache[inn]
            if inn not in unit_meta:
                unit_meta[inn] = AccountingUnitResponse(
                    id=unit_row.id if unit_row else 0,
                    inn=inn,
                    kpp=line.supplier_kpp or (unit_row.kpp if unit_row else None),
                    name=(unit_row.name if unit_row and unit_row.name else None)
                    or line.supplier_name,
                    category_code=unit_row.category_code if unit_row else None,
                    commission_rate_percent=(
                        unit_row.commission_rate_percent if unit_row else None
                    ),
                    is_active=unit_row.is_active if unit_row else True,
                )
            order_map = groups.setdefault(inn, {})
            if order.id not in order_map:
                commission_due = Decimal(str(order.commission_due or 0))
                amount_paid = Decimal(str(order.amount_paid or 0))
                order_map[order.id] = AccountingUnitOrderItem(
                    order_id=order.id,
                    lead_id=order.lead_id,
                    order_no=order.order_no,
                    crm_id=order.crm_id,
                    status=order.status,
                    payment_status=order.payment_status or "unpaid",
                    amount_paid=amount_paid,
                    commission_due=commission_due,
                    lavka_line_volume=Decimal("0"),
                    line_count=0,
                    lines=[],
                    buyer_inn=order.buyer_inn,
                    buyer_name=order.buyer_name,
                    source_filename=order.source_filename,
                    manager_user_id=manager_id,
                    manager_full_name=manager_name,
                    contact_name=contact_name,
                    submitted_at=order.submitted_at,
                    created_at=order.created_at,
                    submission_error=order.submission_error,
                )
            item = order_map[order.id]
            item.lines.append(
                AccountingOrderLineBrief(
                    line_id=line.id,
                    line_no=line.line_no,
                    document_date=line.document_date,
                    amount=Decimal(str(line.amount)),
                    document_number=line.document_number,
                ),
            )
            item.line_count = len(item.lines)
            item.lavka_line_volume += Decimal(str(line.amount))

        grouped: list[AccountingUnitOrderGroup] = []
        for inn, order_map in groups.items():
            orders = sorted(order_map.values(), key=lambda row: row.created_at, reverse=True)
            grouped.append(
                AccountingUnitOrderGroup(unit=unit_meta[inn], orders=orders),
            )
        grouped.sort(key=lambda row: (row.unit.name or row.unit.inn).casefold())

        total = len(grouped)
        page = grouped[offset : offset + limit]
        return AccountingUnitOrdersResponse(items=page, total=total, limit=limit, offset=offset)

    async def list_order_lines(
        self,
        actor: User,
        *,
        supplier_inn: str | None,
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
            "status": _ACCOUNTING_ORDER_STATUS,
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
        if order is None or order.status != _ACCOUNTING_ORDER_STATUS:
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
        supplier_inns = await self._visible_supplier_inns(actor, active_only=False)
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
        supplier_inns = await self._visible_supplier_inns(actor, active_only=False)
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

    async def update_requirement_status(
        self,
        actor: User,
        requirement_id: int,
        status: str,
    ) -> AccountingRequirementResponse:
        supplier_inns = await self._visible_supplier_inns(actor, active_only=False)
        row = await self._repo.get_requirement(requirement_id)
        if row is None:
            raise NotFound(message="Требование не найдено")
        if supplier_inns is not None and row.supplier_inn not in supplier_inns:
            raise NotFound(message="Требование не найдено")
        row.status = status
        await self._session.flush()
        await self._session.commit()
        await self._session.refresh(row)
        return self._requirement_to_response(row)

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

        unit = await self._repo.get_unit_by_inn_any(body.supplier_inn.strip())
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
            filename = pdf_filename or body.pdf_filename or "requirement.pdf"
            mime_type = "application/octet-stream"
            meta_mime = (body.metadata or {}).get("mime_type")
            if isinstance(meta_mime, str) and meta_mime.strip():
                mime_type = meta_mime.strip()
            elif raw_pdf.startswith(b"%PDF"):
                mime_type = "application/pdf"
            elif raw_pdf.startswith(b"PK"):
                mime_type = "application/zip"
            else:
                stripped = raw_pdf.lstrip()
                if stripped.startswith(b"<?xml") or stripped.startswith(b"<"):
                    mime_type = "application/xml"
                elif filename.lower().endswith(".pdf"):
                    mime_type = "application/pdf"
                elif filename.lower().endswith(".zip"):
                    mime_type = "application/zip"
                elif filename.lower().endswith(".xml"):
                    mime_type = "application/xml"
            files = FilesService(self._session)
            uploaded = await files.create_upload(
                uploaded_by=None,
                data=raw_pdf,
                original_name=filename,
                mime_type=mime_type,
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

    async def list_unit_owners(self, actor: User) -> AccountingUnitOwnerListResponse:
        if not self._is_chief(actor):
            raise PermissionDenied()
        accountants = await self._repo.list_accountant_users()
        rows = await self._repo.list_unit_owner_rows()
        periods_by_inn = await self._repo.list_period_codes_by_inns(
            [unit.inn for unit, _, _ in rows],
        )
        deduped: dict[int, AccountingUnitOwnerRow] = {}
        for unit, accountant_id, accountant_name in rows:
            if unit.id in deduped:
                continue
            deduped[unit.id] = AccountingUnitOwnerRow(
                unit_id=unit.id,
                inn=unit.inn,
                name=unit.name,
                category_code=unit.category_code,
                commission_rate_percent=unit.commission_rate_percent,
                is_active=bool(unit.is_active),
                period_codes=periods_by_inn.get(unit.inn, []),
                accountant_user_id=accountant_id,
                accountant_full_name=accountant_name,
            )
        items = sorted(
            deduped.values(),
            key=lambda row: (
                0 if row.is_active else 1,
                0 if row.accountant_user_id is None else 1,
                (row.name or row.inn).casefold(),
            ),
        )
        return AccountingUnitOwnerListResponse(
            items=items,
            accountants=[
                AccountingAccountantOption(user_id=user.id, full_name=user.full_name)
                for user in accountants
            ],
        )

    async def assign_unit_owner(
        self,
        actor: User,
        unit_id: int,
        accountant_user_id: int | None,
    ) -> AccountingUnitOwnerRow:
        if not self._is_chief(actor):
            raise PermissionDenied()
        units = await self._repo.get_units_by_ids([unit_id], active_only=False)
        unit = units.get(unit_id)
        if unit is None:
            raise NotFound(message="Лавка не найдена")
        accountant_name: str | None = None
        if accountant_user_id is not None:
            accountants = await self._repo.list_accountant_users()
            target = next((user for user in accountants if user.id == accountant_user_id), None)
            if target is None:
                raise ValidationError(message="Бухгалтер не найден")
            accountant_name = target.full_name
        await self._repo.set_unit_owner(unit_id, accountant_user_id, assigned_by=actor.id)
        await self._session.commit()
        periods_by_inn = await self._repo.list_period_codes_by_inns([unit.inn])
        return AccountingUnitOwnerRow(
            unit_id=unit.id,
            inn=unit.inn,
            name=unit.name,
            category_code=unit.category_code,
            commission_rate_percent=unit.commission_rate_percent,
            is_active=bool(unit.is_active),
            period_codes=periods_by_inn.get(unit.inn, []),
            accountant_user_id=accountant_user_id,
            accountant_full_name=accountant_name,
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
        units = await self._repo.get_units_by_ids(unique_ids, active_only=False)
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
