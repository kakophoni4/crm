from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.db.models.department import Department
from app.modules.db.models.group import Group
from app.modules.db.models.user import User


class DepartmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self) -> list[Department]:
        result = await self._session.execute(
            select(Department).order_by(Department.name.asc()),
        )
        return list(result.scalars().all())

    async def get_by_id(self, department_id: int) -> Department | None:
        result = await self._session.execute(
            select(Department).where(Department.id == department_id),
        )
        return result.scalar_one_or_none()

    async def count_groups(self, department_id: int) -> int:
        result = await self._session.execute(
            select(func.count()).select_from(Group).where(Group.department_id == department_id),
        )
        return int(result.scalar_one())

    async def count_users(self, department_id: int) -> int:
        result = await self._session.execute(
            select(func.count()).select_from(User).where(User.department_id == department_id),
        )
        return int(result.scalar_one())

    async def add(self, department: Department) -> Department:
        self._session.add(department)
        await self._session.flush()
        await self._session.refresh(department)
        return department

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()
