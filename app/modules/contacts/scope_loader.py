from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.db.models.department import Department
from app.modules.db.models.enums import UserRole, UserStatus
from app.modules.db.models.group import Group
from app.modules.db.models.user import User
from app.modules.rbac.scope import ScopeContext


class ScopeLoader:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def load(self, actor: User) -> ScopeContext:
        role = actor.role if isinstance(actor.role, UserRole) else UserRole(str(actor.role))
        if role == UserRole.ADMIN:
            return ScopeContext(actor=actor)

        group_member_ids: frozenset[int] = frozenset()
        if actor.group_id is not None:
            result = await self._session.execute(
                select(User.id).where(
                    User.group_id == actor.group_id,
                    User.status == UserStatus.ACTIVE,
                ),
            )
            group_member_ids = frozenset(result.scalars().all())

        department_user_ids: frozenset[int] = frozenset()
        department_group_ids: frozenset[int] = frozenset()
        department_senior_id: int | None = None

        if actor.department_id is not None:
            users_result = await self._session.execute(
                select(User.id)
                .outerjoin(Group, User.group_id == Group.id)
                .where(
                    User.status == UserStatus.ACTIVE,
                    or_(
                        User.department_id == actor.department_id,
                        Group.department_id == actor.department_id,
                    ),
                ),
            )
            department_user_ids = frozenset(users_result.scalars().all())

            groups_result = await self._session.execute(
                select(Group.id).where(Group.department_id == actor.department_id),
            )
            department_group_ids = frozenset(groups_result.scalars().all())

            head_result = await self._session.execute(
                select(Department.head_user_id).where(Department.id == actor.department_id),
            )
            department_senior_id = head_result.scalar_one_or_none()

        return ScopeContext(
            actor=actor,
            group_member_ids=group_member_ids,
            department_user_ids=department_user_ids,
            department_senior_id=department_senior_id,
            department_group_ids=department_group_ids,
        )
