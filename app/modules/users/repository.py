from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.db.models.enums import UserRole
from app.modules.db.models.group import Group
from app.modules.db.models.user import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_users(
        self,
        *,
        role: UserRole | None,
        group_id: int | None,
        department_id: int | None,
        q: str | None,
        limit: int,
    ) -> list[User]:
        stmt = select(User).order_by(User.full_name.asc(), User.id.asc()).limit(limit)
        if role is not None:
            stmt = stmt.where(User.role == role.value)
        if group_id is not None:
            stmt = stmt.where(User.group_id == group_id)
        if department_id is not None:
            stmt = stmt.where(User.department_id == department_id)
        if q:
            pattern = f"%{q.strip()}%"
            stmt = stmt.where(
                or_(
                    User.full_name.ilike(pattern),
                    User.email.ilike(pattern),
                    User.username.ilike(pattern),
                ),
            )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, user_id: int) -> User | None:
        result = await self._session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_group(self, group_id: int) -> Group | None:
        result = await self._session.execute(select(Group).where(Group.id == group_id))
        return result.scalar_one_or_none()

    async def add(self, user: User) -> User:
        self._session.add(user)
        await self._session.flush()
        await self._session.refresh(user)
        return user

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()
