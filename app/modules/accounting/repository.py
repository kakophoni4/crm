from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import Select, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.db.models.contact import Contact
from app.modules.db.models.contact_group_assignment import ContactGroupAssignment
from app.modules.db.models.enums import UserRole, UserStatus
from app.modules.db.models.lead import Lead
from app.modules.db.models.lead_opt_order import LeadOptOrder, LeadOptOrderLine
from app.modules.db.models.opt_accountant_unit_assignment import OptAccountantUnitAssignment
from app.modules.db.models.opt_requirement import OptRequirement
from app.modules.db.models.opt_unit import OptUnit
from app.modules.db.models.opt_unit_period import OptUnitPeriodAvailability
from app.modules.db.models.user import User


class AccountingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_active_units(self) -> list[OptUnit]:
        result = await self._session.execute(
            select(OptUnit).where(OptUnit.is_active.is_(True)).order_by(OptUnit.name, OptUnit.inn),
        )
        return list(result.scalars().all())

    async def list_assigned_unit_ids(self, user_id: int) -> list[int]:
        result = await self._session.execute(
            select(OptAccountantUnitAssignment.unit_id).where(
                OptAccountantUnitAssignment.user_id == user_id,
            ),
        )
        return [int(row) for row in result.scalars().all()]

    async def list_assignments_for_users(self, user_ids: list[int]) -> list[OptAccountantUnitAssignment]:
        if not user_ids:
            return []
        result = await self._session.execute(
            select(OptAccountantUnitAssignment)
            .where(OptAccountantUnitAssignment.user_id.in_(user_ids))
            .order_by(OptAccountantUnitAssignment.user_id),
        )
        return list(result.scalars().all())

    async def list_accountant_users(self) -> list[User]:
        result = await self._session.execute(
            select(User)
            .where(
                User.role.in_((UserRole.ACCOUNTANT, UserRole.CHIEF_ACCOUNTANT)),
                User.status == UserStatus.ACTIVE,
            )
            .order_by(User.full_name),
        )
        return list(result.scalars().all())

    async def replace_user_assignments(
        self,
        user_id: int,
        unit_ids: list[int],
        *,
        assigned_by: int,
    ) -> None:
        existing = await self._session.execute(
            select(OptAccountantUnitAssignment).where(
                OptAccountantUnitAssignment.user_id == user_id,
            ),
        )
        for row in existing.scalars().all():
            await self._session.delete(row)
        for unit_id in sorted(set(unit_ids)):
            self._session.add(
                OptAccountantUnitAssignment(
                    user_id=user_id,
                    unit_id=unit_id,
                    assigned_by=assigned_by,
                ),
            )
        await self._session.flush()

    def _order_lines_query(
        self,
        *,
        supplier_inns: set[str] | None,
        supplier_inn: str | None,
        status: str | None,
        manager_user_id: int | None,
        date_from: date | None,
        date_to: date | None,
        q: str | None,
        period_code: str | None = None,
    ) -> Select[Any]:
        stmt = (
            select(
                LeadOptOrderLine,
                LeadOptOrder,
                Lead,
                Contact.full_name,
                User.id,
                User.full_name,
            )
            .join(LeadOptOrder, LeadOptOrderLine.order_id == LeadOptOrder.id)
            .join(Lead, LeadOptOrder.lead_id == Lead.id)
            .join(Contact, Lead.contact_id == Contact.id)
            .outerjoin(
                ContactGroupAssignment,
                (ContactGroupAssignment.contact_id == Lead.contact_id)
                & (ContactGroupAssignment.group_id == Lead.group_id),
            )
            .outerjoin(User, User.id == ContactGroupAssignment.owner_user_id)
        )
        if supplier_inns is not None:
            if not supplier_inns:
                stmt = stmt.where(False)
            else:
                stmt = stmt.where(LeadOptOrderLine.supplier_inn.in_(supplier_inns))
        if supplier_inn:
            stmt = stmt.where(LeadOptOrderLine.supplier_inn == supplier_inn)
        if status:
            stmt = stmt.where(LeadOptOrder.status == status)
        if period_code:
            stmt = stmt.where(LeadOptOrder.period_code == period_code.strip())
        if manager_user_id is not None:
            stmt = stmt.where(User.id == manager_user_id)
        if date_from is not None:
            stmt = stmt.where(LeadOptOrder.created_at >= datetime.combine(date_from, datetime.min.time()))
        if date_to is not None:
            stmt = stmt.where(LeadOptOrder.created_at < datetime.combine(date_to, datetime.max.time()))
        if q:
            pattern = f"%{q.strip()}%"
            stmt = stmt.where(
                (LeadOptOrder.crm_id.ilike(pattern))
                | (LeadOptOrder.buyer_inn.ilike(pattern))
                | (LeadOptOrder.buyer_name.ilike(pattern))
                | (LeadOptOrderLine.supplier_inn.ilike(pattern))
                | (LeadOptOrderLine.supplier_name.ilike(pattern))
                | (Contact.full_name.ilike(pattern))
                | (User.full_name.ilike(pattern)),
            )
        return stmt.order_by(LeadOptOrder.created_at.desc(), LeadOptOrderLine.line_no)

    async def count_order_lines(self, **filters: Any) -> int:
        base = self._order_lines_query(**filters).subquery()
        result = await self._session.execute(select(func.count()).select_from(base))
        return int(result.scalar_one())

    async def list_order_lines(
        self,
        *,
        limit: int,
        offset: int,
        **filters: Any,
    ) -> list[tuple[LeadOptOrderLine, LeadOptOrder, Lead, str | None, int | None, str | None]]:
        stmt = self._order_lines_query(**filters).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.all())

    async def list_order_lines_all(
        self,
        **filters: Any,
    ) -> list[tuple[LeadOptOrderLine, LeadOptOrder, Lead, str | None, int | None, str | None]]:
        result = await self._session.execute(self._order_lines_query(**filters))
        return list(result.all())

    async def list_unit_owner_rows(
        self,
        *,
        active_only: bool = False,
    ) -> list[tuple[OptUnit, int | None, str | None]]:
        stmt = (
            select(OptUnit, User.id, User.full_name)
            .outerjoin(
                OptAccountantUnitAssignment,
                OptAccountantUnitAssignment.unit_id == OptUnit.id,
            )
            .outerjoin(User, User.id == OptAccountantUnitAssignment.user_id)
        )
        if active_only:
            stmt = stmt.where(OptUnit.is_active.is_(True))
        stmt = stmt.order_by(OptUnit.is_active.desc(), OptUnit.name, OptUnit.inn)
        result = await self._session.execute(stmt)
        return list(result.all())

    async def set_unit_owner(
        self,
        unit_id: int,
        accountant_user_id: int | None,
        *,
        assigned_by: int,
    ) -> None:
        existing = await self._session.execute(
            select(OptAccountantUnitAssignment).where(
                OptAccountantUnitAssignment.unit_id == unit_id,
            ),
        )
        for row in existing.scalars().all():
            await self._session.delete(row)
        if accountant_user_id is not None:
            self._session.add(
                OptAccountantUnitAssignment(
                    user_id=accountant_user_id,
                    unit_id=unit_id,
                    assigned_by=assigned_by,
                ),
            )
        await self._session.flush()

    async def get_order_for_registry(self, order_id: int) -> LeadOptOrder | None:
        from sqlalchemy.orm import selectinload

        result = await self._session.execute(
            select(LeadOptOrder)
            .where(LeadOptOrder.id == order_id)
            .options(selectinload(LeadOptOrder.lines)),
        )
        return result.scalar_one_or_none()

    async def order_visible_for_supplier_inns(
        self,
        order_id: int,
        supplier_inns: set[str] | None,
    ) -> bool:
        if supplier_inns is None:
            return True
        if not supplier_inns:
            return False
        result = await self._session.execute(
            select(func.count())
            .select_from(LeadOptOrderLine)
            .where(
                LeadOptOrderLine.order_id == order_id,
                LeadOptOrderLine.supplier_inn.in_(supplier_inns),
            ),
        )
        return int(result.scalar_one()) > 0

    def _requirements_query(
        self,
        *,
        supplier_inns: set[str] | None,
        supplier_inn: str | None,
        status: str | None,
        q: str | None,
    ) -> Select[Any]:
        stmt = select(OptRequirement)
        if supplier_inns is not None:
            if not supplier_inns:
                stmt = stmt.where(False)
            else:
                stmt = stmt.where(OptRequirement.supplier_inn.in_(supplier_inns))
        if supplier_inn:
            stmt = stmt.where(OptRequirement.supplier_inn == supplier_inn)
        if status:
            stmt = stmt.where(OptRequirement.status == status)
        if q:
            pattern = f"%{q.strip()}%"
            stmt = stmt.where(
                (OptRequirement.title.ilike(pattern))
                | (OptRequirement.external_id.ilike(pattern))
                | (OptRequirement.supplier_inn.ilike(pattern))
                | (OptRequirement.supplier_name.ilike(pattern)),
            )
        return stmt.order_by(OptRequirement.received_at.desc(), OptRequirement.id.desc())

    async def count_requirements(self, **filters: Any) -> int:
        base = self._requirements_query(**filters).subquery()
        result = await self._session.execute(select(func.count()).select_from(base))
        return int(result.scalar_one())

    async def list_requirements(
        self,
        *,
        limit: int,
        offset: int,
        **filters: Any,
    ) -> list[OptRequirement]:
        stmt = self._requirements_query(**filters).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_requirement(self, requirement_id: int) -> OptRequirement | None:
        result = await self._session.execute(
            select(OptRequirement).where(OptRequirement.id == requirement_id),
        )
        return result.scalar_one_or_none()

    async def get_requirement_by_external_id(self, external_id: str) -> OptRequirement | None:
        result = await self._session.execute(
            select(OptRequirement).where(OptRequirement.external_id == external_id),
        )
        return result.scalar_one_or_none()

    async def add_requirement(self, row: OptRequirement) -> OptRequirement:
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return row

    async def get_units_by_ids(
        self,
        unit_ids: list[int],
        *,
        active_only: bool = True,
    ) -> dict[int, OptUnit]:
        if not unit_ids:
            return {}
        stmt = select(OptUnit).where(OptUnit.id.in_(unit_ids))
        if active_only:
            stmt = stmt.where(OptUnit.is_active.is_(True))
        result = await self._session.execute(stmt)
        return {unit.id: unit for unit in result.scalars().all()}

    async def get_unit_by_inn(self, inn: str) -> OptUnit | None:
        result = await self._session.execute(
            select(OptUnit).where(OptUnit.inn == inn, OptUnit.is_active.is_(True)),
        )
        return result.scalar_one_or_none()

    async def get_unit_by_inn_any(self, inn: str) -> OptUnit | None:
        result = await self._session.execute(
            select(OptUnit).where(OptUnit.inn == inn),
        )
        return result.scalar_one_or_none()

    async def add_unit(self, unit: OptUnit) -> OptUnit:
        self._session.add(unit)
        await self._session.flush()
        await self._session.refresh(unit)
        return unit

    async def count_active_orders_for_supplier_inn(self, inn: str) -> int:
        """Non-deleted OPT orders that still have lines for this lavka INN."""
        result = await self._session.execute(
            select(func.count(func.distinct(LeadOptOrder.id)))
            .select_from(LeadOptOrderLine)
            .join(LeadOptOrder, LeadOptOrder.id == LeadOptOrderLine.order_id)
            .where(
                LeadOptOrderLine.supplier_inn == inn,
                LeadOptOrder.deleted_at.is_(None),
            ),
        )
        return int(result.scalar_one() or 0)

    async def delete_unit(self, unit: OptUnit) -> None:
        await self._session.execute(
            delete(OptUnitPeriodAvailability).where(OptUnitPeriodAvailability.inn == unit.inn),
        )
        await self._session.delete(unit)
        await self._session.flush()

    async def list_period_codes_by_inns(self, inns: list[str]) -> dict[str, list[str]]:
        if not inns:
            return {}
        result = await self._session.execute(
            select(OptUnitPeriodAvailability.inn, OptUnitPeriodAvailability.period_code)
            .where(OptUnitPeriodAvailability.inn.in_(inns))
            .order_by(OptUnitPeriodAvailability.period_code),
        )
        out: dict[str, list[str]] = {}
        for inn, period_code in result.all():
            out.setdefault(str(inn), []).append(str(period_code))
        return out

    async def replace_unit_periods(
        self,
        *,
        unit_id: int,
        inn: str,
        period_codes: list[str],
    ) -> list[str]:
        # DELETE must flush before INSERT — same (inn, period_code) unique key
        # otherwise SQLAlchemy UOW can insert first and hit UniqueViolation.
        await self._session.execute(
            delete(OptUnitPeriodAvailability).where(OptUnitPeriodAvailability.inn == inn),
        )
        await self._session.flush()
        unique = sorted({code for code in period_codes if code})
        for code in unique:
            self._session.add(
                OptUnitPeriodAvailability(
                    inn=inn,
                    period_code=code,
                    unit_id=unit_id,
                ),
            )
        await self._session.flush()
        return unique
