from __future__ import annotations

import base64
import binascii
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.accounting.repository import AccountingRepository
from app.modules.accounting.requirement_deadline import resolve_response_due_date
from app.modules.accounting.requirement_kinds import (
    DOC_KIND_ACCOUNT_BLOCK,
    is_account_block_notice,
)
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
from app.modules.db.models.enums import AuditAction, UserRole
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
            volume_limit=(
                Decimal(str(unit.volume_limit))
                if unit.volume_limit is not None
                else None
            ),
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
            volume_limit=body.volume_limit,
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
            and body.volume_limit is None
            and body.clear_volume_limit is None
            and body.name is None
            and body.category_code is None
            and body.period_codes is None
            and body.is_active is None
        ):
            raise ValidationError(message="Нет полей для обновления")

        if body.commission_rate_percent is not None:
            unit.commission_rate_percent = body.commission_rate_percent
        if body.clear_volume_limit:
            unit.volume_limit = None
        elif body.volume_limit is not None:
            unit.volume_limit = body.volume_limit
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

    async def delete_unit(self, actor: User, unit_id: int) -> None:
        if not self._is_chief(actor):
            raise PermissionDenied()

        units = await self._repo.get_units_by_ids([unit_id], active_only=False)
        unit = units.get(unit_id)
        if unit is None:
            raise NotFound(message="Лавка не найдена")

        active_orders = await self._repo.count_active_orders_for_supplier_inn(unit.inn)
        if active_orders > 0:
            raise ValidationError(
                message=(
                    f"Нельзя удалить лавку: на ИНН {unit.inn} висит "
                    f"{active_orders} активных заявок"
                ),
                details={"inn": unit.inn, "active_orders": active_orders},
            )

        await self._repo.delete_unit(unit)
        await self._session.commit()

    async def list_orders_by_units(
        self,
        actor: User,
        *,
        supplier_inn: str | None,
        manager_user_id: int | None,
        date_from: date | None,
        date_to: date | None,
        q: str | None,
        period_code: str | None,
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
            "period_code": period_code,
        }
        inns = await self._repo.list_order_supplier_inns(**filters)
        units_by_inn = await self._repo.get_units_by_inns(inns)
        inns.sort(
            key=lambda inn: (units_by_inn[inn].name or inn if inn in units_by_inn else inn).casefold(),
        )
        total = len(inns)
        page_inns = inns[offset : offset + limit]
        if not page_inns:
            return AccountingUnitOrdersResponse(items=[], total=total, limit=limit, offset=offset)
        page_filters = {**filters, "supplier_inns": set(page_inns), "supplier_inn": None}
        rows = await self._repo.list_order_lines_all(**page_filters)
        unit_cache: dict[str, OptUnit | None] = {inn: units_by_inn.get(inn) for inn in page_inns}
        groups: dict[str, dict[int, AccountingUnitOrderItem]] = {}
        unit_meta: dict[str, AccountingUnitResponse] = {}

        for line, order, _lead, contact_name, manager_id, manager_name in rows:
            inn = line.supplier_inn
            unit_row = unit_cache.get(inn)
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
                    volume_limit=(
                        Decimal(str(unit_row.volume_limit))
                        if unit_row and unit_row.volume_limit is not None
                        else None
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
                    period_code=getattr(order, "period_code", None),
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
            volume_sum = sum(
                (row.lavka_line_volume for row in orders),
                Decimal("0"),
            ).quantize(Decimal("0.01"))
            grouped.append(
                AccountingUnitOrderGroup(
                    unit=unit_meta[inn],
                    orders=orders,
                    orders_count=len(orders),
                    orders_volume_sum=volume_sum,
                ),
            )
        grouped.sort(key=lambda row: (row.unit.name or row.unit.inn).casefold())
        return AccountingUnitOrdersResponse(items=grouped, total=total, limit=limit, offset=offset)

    async def list_order_lines(
        self,
        actor: User,
        *,
        supplier_inn: str | None,
        manager_user_id: int | None,
        date_from: date | None,
        date_to: date | None,
        q: str | None,
        period_code: str | None = None,
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
            "period_code": period_code,
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
                    period_code=getattr(order, "period_code", None),
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

    async def update_order_period(
        self,
        actor: User,
        order_id: int,
        period_code: str,
    ) -> tuple[int, str]:
        from app.modules.leads.opt.period_access import (
            assert_supplier_inns_allowed_for_period,
            normalize_requested_period,
        )
        from app.modules.leads.opt.periods import normalize_period_code

        supplier_inns = await self._visible_supplier_inns(actor)
        if not await self._repo.order_visible_for_supplier_inns(order_id, supplier_inns):
            raise NotFound(message="Заявка не найдена")
        order = await self._repo.get_order_for_registry(order_id)
        if order is None or order.status != _ACCOUNTING_ORDER_STATUS:
            raise NotFound(message="Заявка не найдена")
        new_code = normalize_requested_period(period_code)
        current = normalize_period_code(getattr(order, "period_code", None) or "")
        if current == new_code:
            return order.id, new_code
        await assert_supplier_inns_allowed_for_period(
            self._session,
            period_code=new_code,
            supplier_inns=[line.supplier_inn for line in order.lines],
        )
        order.period_code = new_code
        await self._session.flush()
        return order.id, new_code

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
        # Прописать срок, если СБИС не отдал: без PDF — 5 раб. дней от получения.
        backfilled = False
        for row in rows:
            if row.response_due_date is None and not is_account_block_notice(
                title=row.title,
                filename=str((row.metadata_json or {}).get("storage_file_name") or ""),
                metadata=row.metadata_json,
            ):
                before = row.response_due_date
                self._fill_response_due_from_pdf(row, pdf_bytes=None)
                if row.response_due_date is not None and row.response_due_date != before:
                    backfilled = True
        if backfilled:
            await self._session.commit()
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

    def _apply_requirement_meta_fields(
        self,
        row: OptRequirement,
        body: AccountingRequirementIngestRequest,
    ) -> None:
        title = (body.title or "").strip()
        if title:
            row.title = title
        if body.description is not None:
            row.description = body.description.strip() or None
        if body.response_due_date is not None:
            row.response_due_date = body.response_due_date
        if body.receipt_due_date is not None:
            row.receipt_due_date = body.receipt_due_date
        notice = is_account_block_notice(
            title=row.title,
            filename=str((body.metadata or {}).get("storage_file_name") or ""),
            metadata={**(row.metadata_json or {}), **(body.metadata or {})},
        )
        if notice:
            row.reply_status = "none"
        elif body.reply_status:
            row.reply_status = body.reply_status
        if body.reply_error is not None:
            row.reply_error = body.reply_error
        if body.replied_at is not None:
            replied = body.replied_at
            if replied.tzinfo is not None:
                replied = replied.astimezone(UTC).replace(tzinfo=None)
            row.replied_at = replied
        if body.sbis_requirement_id is not None:
            row.sbis_requirement_id = body.sbis_requirement_id
        if body.metadata:
            row.metadata_json = {**(row.metadata_json or {}), **body.metadata}

    def _received_on(self, row: OptRequirement) -> date | None:
        meta = row.metadata_json or {}
        for key in ("document_date", "received_date"):
            raw = meta.get(key)
            if isinstance(raw, str) and raw.strip():
                try:
                    return date.fromisoformat(raw.strip()[:10])
                except ValueError:
                    pass
        if row.received_at is not None:
            return row.received_at.date()
        if row.created_at is not None:
            return row.created_at.date()
        return None

    def _fill_response_due_from_pdf(
        self,
        row: OptRequirement,
        *,
        pdf_bytes: bytes | None,
        force_default: bool = False,
    ) -> None:
        """Если СБИС не дал срок — парсим PDF или ставим 5 рабочих дней от получения."""
        if row.response_due_date is not None and not force_default:
            return
        parsed = resolve_response_due_date(
            existing=row.response_due_date,
            received_on=self._received_on(row),
            pdf_bytes=pdf_bytes,
        )
        if parsed.response_due_date is None:
            return
        row.response_due_date = parsed.response_due_date
        meta = dict(row.metadata_json or {})
        meta["response_due_source"] = parsed.source
        if parsed.working_days is not None:
            meta["response_due_working_days"] = parsed.working_days
        row.metadata_json = meta

    async def _ensure_requirement_response_due(self, row: OptRequirement) -> date | None:
        if is_account_block_notice(
            title=row.title,
            filename=str((row.metadata_json or {}).get("storage_file_name") or ""),
            metadata=row.metadata_json,
        ):
            return row.response_due_date
        if row.response_due_date is not None:
            return row.response_due_date
        pdf_bytes: bytes | None = None
        if row.pdf_file_id is not None:
            try:
                files = FilesService(self._session)
                pdf_bytes, _, _ = await files.get_bytes(row.pdf_file_id)
            except Exception:
                pdf_bytes = None
        self._fill_response_due_from_pdf(row, pdf_bytes=pdf_bytes)
        if row.response_due_date is None:
            # последний резерв — 5 раб. дней от сегодня / received
            parsed = resolve_response_due_date(
                existing=None,
                received_on=self._received_on(row) or date.today(),
                pdf_bytes=None,
            )
            row.response_due_date = parsed.response_due_date
            meta = dict(row.metadata_json or {})
            meta["response_due_source"] = parsed.source
            meta["response_due_working_days"] = parsed.working_days
            row.metadata_json = meta
        await self._session.flush()
        return row.response_due_date

    async def ingest_requirement(
        self,
        body: AccountingRequirementIngestRequest,
        *,
        pdf_bytes: bytes | None,
        pdf_filename: str | None,
    ) -> AccountingRequirementIngestResponse:
        existing = await self._repo.get_requirement_by_external_id(body.external_id.strip())
        notice = is_account_block_notice(
            title=body.title,
            filename=pdf_filename or body.pdf_filename,
            metadata=body.metadata,
        )
        if notice:
            body.reply_status = "none"
            body.replied_at = None
            pdf_bytes = None
            meta = dict(body.metadata or {})
            meta["doc_kind"] = DOC_KIND_ACCOUNT_BLOCK
            meta["can_reply"] = False
            body.metadata = meta
        if existing is not None:
            self._apply_requirement_meta_fields(existing, body)
            if not notice and existing.response_due_date is None:
                self._fill_response_due_from_pdf(existing, pdf_bytes=pdf_bytes)
            await self._session.flush()
            await self._session.commit()
            return AccountingRequirementIngestResponse(
                id=existing.id,
                external_id=existing.external_id,
                created=False,
            )

        unit = await self._repo.get_unit_by_inn_any(body.supplier_inn.strip())
        supplier_kpp = body.supplier_kpp or (unit.kpp if unit else None)
        supplier_name = body.supplier_name or (unit.name if unit else None)

        file_id: int | None = None
        raw_pdf = None if notice else pdf_bytes
        if raw_pdf is None and not notice and body.pdf_base64:
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

        # Column is TIMESTAMP WITHOUT TIME ZONE — store naive UTC only.
        received_at = body.received_at or datetime.now(UTC)
        if received_at.tzinfo is not None:
            received_at = received_at.astimezone(UTC).replace(tzinfo=None)
        row = OptRequirement(
            external_id=body.external_id.strip(),
            supplier_inn=body.supplier_inn.strip(),
            supplier_kpp=supplier_kpp,
            supplier_name=supplier_name,
            title=body.title.strip(),
            description=body.description.strip() if body.description else None,
            status=body.status or "new",
            response_due_date=body.response_due_date,
            receipt_due_date=body.receipt_due_date,
            reply_status=body.reply_status or "none",
            reply_error=body.reply_error,
            replied_at=body.replied_at,
            sbis_requirement_id=body.sbis_requirement_id,
            pdf_file_id=file_id,
            metadata_json=body.metadata or {},
            received_at=received_at,
        )
        if row.replied_at is not None and row.replied_at.tzinfo is not None:
            row.replied_at = row.replied_at.astimezone(UTC).replace(tzinfo=None)
        if not notice:
            self._fill_response_due_from_pdf(row, pdf_bytes=raw_pdf)
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
                volume_limit=(
                    Decimal(str(unit.volume_limit))
                    if unit.volume_limit is not None
                    else None
                ),
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
            volume_limit=(
                Decimal(str(unit.volume_limit))
                if unit.volume_limit is not None
                else None
            ),
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
        from datetime import date as date_cls
        from datetime import timedelta

        pdf_name = row.pdf_file.original_name if row.pdf_file is not None else None
        today = date_cls.today()
        due = row.response_due_date
        notice = is_account_block_notice(
            title=row.title,
            filename=pdf_name or str((row.metadata_json or {}).get("storage_file_name") or ""),
            metadata=row.metadata_json,
        )
        is_overdue = bool(
            not notice
            and due is not None
            and due < today
            and (row.reply_status or "none") in {"none", "error"}
        )
        due_soon = bool(
            not notice
            and due is not None
            and today <= due <= today + timedelta(days=1)
            and (row.reply_status or "none") in {"none", "error"}
        )
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
            response_due_date=row.response_due_date,
            receipt_due_date=row.receipt_due_date,
            reply_status=row.reply_status or "none",
            reply_error=row.reply_error,
            replied_at=row.replied_at,
            sbis_requirement_id=row.sbis_requirement_id,
            has_pdf=row.pdf_file_id is not None,
            pdf_filename=pdf_name,
            metadata=row.metadata_json or {},
            received_at=row.received_at,
            created_at=row.created_at,
            is_overdue=is_overdue,
            due_soon=due_soon,
            can_reply=not notice,
            doc_kind=DOC_KIND_ACCOUNT_BLOCK if notice else "requirement",
        )

    async def requirements_due_summary(self, actor: User) -> AccountingRequirementDueSummary:
        from datetime import date as date_cls
        from datetime import timedelta

        from app.modules.accounting.schemas import AccountingRequirementDueSummary

        supplier_inns = await self._visible_supplier_inns(actor, active_only=False)
        rows = await self._repo.list_requirements(
            limit=500,
            offset=0,
            supplier_inns=supplier_inns,
            supplier_inn=None,
            status=None,
            q=None,
        )
        today = date_cls.today()
        overdue = due_soon = unanswered = 0
        for row in rows:
            if is_account_block_notice(
                title=row.title,
                filename=str((row.metadata_json or {}).get("storage_file_name") or ""),
                metadata=row.metadata_json,
            ):
                continue
            if (row.reply_status or "none") not in {"none", "error"}:
                continue
            unanswered += 1
            due = row.response_due_date
            if due is None:
                continue
            if due < today:
                overdue += 1
            elif due <= today + timedelta(days=1):
                due_soon += 1
        return AccountingRequirementDueSummary(
            overdue=overdue,
            due_soon=due_soon,
            unanswered=unanswered,
        )

    async def reply_requirement(
        self,
        actor: User,
        requirement_id: int,
        *,
        files: list[tuple[str, bytes]],
        dry_run: bool = False,
    ):
        from app.modules.accounting import sbis_norm_client
        from app.modules.accounting.schemas import AccountingRequirementReplyResponse

        supplier_inns = await self._visible_supplier_inns(actor, active_only=False)
        row = await self._repo.get_requirement(requirement_id)
        if row is None:
            raise NotFound(message="Требование не найдено")
        if supplier_inns is not None and row.supplier_inn not in supplier_inns:
            raise NotFound(message="Требование не найдено")
        sbis_id = row.sbis_requirement_id
        if sbis_id is None:
            meta = row.metadata_json or {}
            raw = meta.get("sbis_id")
            if isinstance(raw, int):
                sbis_id = raw
            elif isinstance(raw, str) and raw.isdigit():
                sbis_id = int(raw)
        if sbis_id is None:
            raise ValidationError(message="Нет связи с документом sbis-norm")
        if is_account_block_notice(
            title=row.title,
            filename=str((row.metadata_json or {}).get("storage_file_name") or ""),
            metadata=row.metadata_json,
        ):
            raise ValidationError(message="На уведомление о блокировке счёта ответить нельзя")
        if not files:
            raise ValidationError(message="Прикрепите хотя бы один файл")

        import base64 as b64mod

        attachments = [
            {
                "filename": name or f"doc-{idx}.pdf",
                "content_b64": b64mod.b64encode(raw).decode("ascii"),
            }
            for idx, (name, raw) in enumerate(files, start=1)
        ]
        try:
            payload = await sbis_norm_client.reply_requirement(
                sbis_id,
                attachments=attachments,
                dry_run=dry_run,
            )
        except Exception as exc:
            row.reply_status = "error"
            row.reply_error = str(getattr(exc, "message", None) or exc)[:2000]
            await self._session.commit()
            raise

        success = bool(payload.get("success"))
        if dry_run:
            return AccountingRequirementReplyResponse(
                id=row.id,
                reply_status=row.reply_status or "none",
                reply_error=row.reply_error,
                replied_at=row.replied_at,
                dry_run=True,
                success=success,
            )

        if success:
            row.reply_status = "sent"
            row.reply_error = None
            row.replied_at = datetime.now(UTC).replace(tzinfo=None)
            row.sbis_requirement_id = sbis_id
            # После ответа в СБИС уходит из «Непрочитанные» в «Отвеченные».
            row.status = "answered"
            meta = dict(row.metadata_json or {})
            meta["last_reply"] = payload.get("send_meta") or {}
            row.metadata_json = meta
        else:
            row.reply_status = "error"
            row.reply_error = str(payload.get("error") or "reply failed")[:2000]
        await self._session.commit()
        await self._session.refresh(row)
        return AccountingRequirementReplyResponse(
            id=row.id,
            reply_status=row.reply_status or "none",
            reply_error=row.reply_error,
            replied_at=row.replied_at,
            dry_run=False,
            success=success,
        )

    async def _resolve_task_department_id(
        self,
        actor: User,
        assignee: User,
    ) -> int | None:
        """department_id is often null for admin/chief — still need a board dept."""
        from sqlalchemy import select

        from app.modules.db.models.department import Department

        for candidate in (assignee.department_id, actor.department_id):
            if candidate is not None:
                return int(candidate)

        # Any user who already has a department (prefer accountants).
        user_dept = (
            await self._session.execute(
                select(User.department_id)
                .where(
                    User.department_id.is_not(None),
                    User.role.in_(
                        [
                            UserRole.ACCOUNTANT,
                            UserRole.CHIEF_ACCOUNTANT,
                            UserRole.SENIOR,
                            UserRole.ADMIN,
                            UserRole.USER,
                        ],
                    ),
                )
                .order_by(User.id.asc())
                .limit(1),
            )
        ).scalar_one_or_none()
        if user_dept is not None:
            return int(user_dept)

        dept_row = (
            await self._session.execute(
                select(Department.id).order_by(Department.id.asc()).limit(1),
            )
        ).scalar_one_or_none()
        if dept_row is not None:
            return int(dept_row)

        # Last resort: create a default department so FNS tasks are not blocked.
        dept = Department(name="Бухгалтерия")
        self._session.add(dept)
        await self._session.flush()
        return int(dept.id)

    async def list_task_assignees(self, actor: User):
        from sqlalchemy import select

        from app.modules.accounting.schemas import (
            AccountingTaskAssigneeListResponse,
            AccountingTaskAssigneeOption,
        )
        from app.modules.db.models.enums import UserStatus

        result = await self._session.execute(
            select(User)
            .where(
                User.status == UserStatus.ACTIVE,
                User.role.in_(
                    [
                        UserRole.USER,
                        UserRole.GROUP_SENIOR,
                        UserRole.SENIOR,
                        UserRole.ACCOUNTANT,
                        UserRole.CHIEF_ACCOUNTANT,
                        UserRole.ADMIN,
                    ],
                ),
            )
            .order_by(User.full_name)
            .limit(300),
        )
        users = list(result.scalars().all())
        # Текущий пользователь первым — удобно выбрать «себе»
        users.sort(
            key=lambda u: (0 if u.id == actor.id else 1, (u.full_name or "").casefold()),
        )
        items = [
            AccountingTaskAssigneeOption(
                id=u.id,
                full_name=u.full_name,
                role=str(u.role.value if hasattr(u.role, "value") else u.role),
            )
            for u in users
        ]
        return AccountingTaskAssigneeListResponse(items=items)

    async def create_task_from_requirement(
        self,
        actor: User,
        requirement_id: int,
        body,
    ):
        from app.modules.db.models.department_task import DepartmentTask
        from app.modules.db.models.department_task_file import DepartmentTaskFile
        from app.modules.tasks.schemas import TaskResponse
        from app.modules.tasks.service import TaskService
        from app.modules.tasks.types import TaskStatus, TaskType

        supplier_inns = await self._visible_supplier_inns(actor, active_only=False)
        row = await self._repo.get_requirement(requirement_id)
        if row is None:
            raise NotFound(message="Требование не найдено")
        if supplier_inns is not None and row.supplier_inn not in supplier_inns:
            raise NotFound(message="Требование не найдено")

        unit_inn = (body.unit_inn or row.supplier_inn or "").strip()
        unit = await self._repo.get_unit_by_inn_any(unit_inn)
        assignee = await self._session.get(User, body.assignee_id)
        if assignee is None:
            raise ValidationError(message="Исполнитель не найден")
        dept_id = await self._resolve_task_department_id(actor, assignee)
        if dept_id is None:
            raise ValidationError(message="Не удалось определить отдел для задачи")

        response_due = await self._ensure_requirement_response_due(row)
        due_at = body.due_at
        if due_at is None and response_due is not None:
            due_at = datetime(
                response_due.year,
                response_due.month,
                response_due.day,
                18,
                0,
                0,
                tzinfo=UTC,
            )
        task_type = body.task_type if body.task_type in {t.value for t in TaskType} else TaskType.NORMAL.value
        if response_due is not None:
            from datetime import timedelta

            if response_due <= date.today() + timedelta(days=1):
                task_type = TaskType.URGENT.value

        task = DepartmentTask(
            department_id=dept_id,
            title=body.title.strip(),
            description=body.description.strip() if body.description else None,
            task_type=task_type,
            status=TaskStatus.NEW.value,
            source="fns_requirement",
            opt_unit_id=unit.id if unit else None,
            opt_requirement_id=row.id,
            created_by=actor.id,
            assignee_id=assignee.id,
            due_at=due_at,
        )
        self._session.add(task)
        await self._session.flush()
        # PDF требования всегда в задаче; доп. файлы из формы — следом.
        attached: list[int] = []
        if row.pdf_file_id is not None:
            attached.append(int(row.pdf_file_id))
        for fid in body.file_ids or []:
            fid_i = int(fid)
            if fid_i not in attached:
                attached.append(fid_i)
        for fid in attached:
            self._session.add(DepartmentTaskFile(task_id=task.id, file_id=fid))
        task_service = TaskService(self._session)
        await task_service._write_history(
            actor,
            task,
            AuditAction.TASK_CREATE,
            {
                "kind": "create",
                "title": task.title,
                "assignee_id": assignee.id,
                "assignee_name": assignee.full_name,
                "source": "fns_requirement",
            },
        )
        await self._session.commit()
        await self._session.refresh(task)
        response = (await task_service._build_responses([task]))[0]
        from app.realtime.events import publish
        from app.realtime.topics import TASK_CREATED

        payload = task_service._event_payload(task)
        await publish(TASK_CREATED, payload, scope={"user_id": task.assignee_id})
        await publish(TASK_CREATED, payload, scope={"department_id": task.department_id})
        return response
