from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.contacts.scope_loader import ScopeLoader
from app.modules.db.models.department import Department
from app.modules.db.models.enums import UserRole, UserStatus
from app.modules.db.models.group import Group
from app.modules.db.models.user import User
from app.modules.db.models.user_group_membership import UserGroupMembership
from app.modules.groups.schemas import (
    GroupCreateRequest,
    GroupListResponse,
    GroupOut,
    GroupUpdateRequest,
)
from app.modules.rbac.scope import SCOPE_ALL, visible_group_ids
from app.shared.exceptions import Conflict, NotFound, PermissionDenied, ValidationError


class GroupOrgService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _visible_ids(self, actor: User) -> set[int] | str:
        ctx = await ScopeLoader(self._session).load(actor)
        return visible_group_ids(ctx)

    def _ensure_visible(self, group_id: int, visible: set[int] | str) -> None:
        if visible == SCOPE_ALL:
            return
        if not isinstance(visible, set) or group_id not in visible:
            raise NotFound(message="Group not found", details={"id": group_id})

    async def list_groups(
        self,
        actor: User,
        *,
        department_id: int | None,
    ) -> GroupListResponse:
        visible = await self._visible_ids(actor)
        stmt = select(Group).order_by(Group.name.asc())
        if department_id is not None:
            stmt = stmt.where(Group.department_id == department_id)
        result = await self._session.execute(stmt)
        rows = list(result.scalars().all())
        if visible != SCOPE_ALL:
            assert isinstance(visible, set)
            rows = [row for row in rows if row.id in visible]
        return GroupListResponse(items=[GroupOut.model_validate(row) for row in rows])

    async def _get_group(self, group_id: int) -> Group:
        result = await self._session.execute(select(Group).where(Group.id == group_id))
        group = result.scalar_one_or_none()
        if group is None:
            raise NotFound(message="Group not found", details={"id": group_id})
        return group

    def _ensure_senior_department(self, actor: User, department_id: int) -> None:
        role = actor.role if isinstance(actor.role, UserRole) else UserRole(str(actor.role))
        if role == UserRole.ADMIN:
            return
        if role == UserRole.SENIOR:
            if actor.department_id != department_id:
                raise PermissionDenied(
                    message="Senior can only manage groups in own department",
                )
            return
        raise PermissionDenied()

    async def create_group(self, actor: User, body: GroupCreateRequest) -> GroupOut:
        role = actor.role if isinstance(actor.role, UserRole) else UserRole(str(actor.role))
        if role not in (UserRole.ADMIN, UserRole.SENIOR):
            raise PermissionDenied()
        self._ensure_senior_department(actor, body.department_id)

        dept = await self._session.get(Department, body.department_id)
        if dept is None:
            raise ValidationError(
                message="department_id does not exist",
                details={"department_id": body.department_id},
            )

        group = Group(
            name=body.name.strip(),
            department_id=body.department_id,
            created_by=actor.id,
        )
        self._session.add(group)
        try:
            await self._session.flush()
            await self._session.refresh(group)
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise Conflict(message="Group name already exists in department") from exc
        return GroupOut.model_validate(group)

    async def update_group(
        self,
        actor: User,
        group_id: int,
        body: GroupUpdateRequest,
    ) -> GroupOut:
        visible = await self._visible_ids(actor)
        group = await self._get_group(group_id)
        self._ensure_visible(group_id, visible)
        self._ensure_senior_department(actor, group.department_id)

        if body.name is not None:
            group.name = body.name.strip()
        try:
            await self._session.flush()
            await self._session.commit()
            await self._session.refresh(group)
        except IntegrityError as exc:
            await self._session.rollback()
            raise Conflict(message="Group name already exists in department") from exc
        return GroupOut.model_validate(group)

    async def delete_group(self, actor: User, group_id: int) -> GroupOut:
        visible = await self._visible_ids(actor)
        group = await self._get_group(group_id)
        self._ensure_visible(group_id, visible)
        self._ensure_senior_department(actor, group.department_id)

        active_users = await self._session.execute(
            select(func.count(func.distinct(User.id)))
            .select_from(User)
            .outerjoin(UserGroupMembership, UserGroupMembership.user_id == User.id)
            .where(
                User.status == UserStatus.ACTIVE,
                or_(
                    User.group_id == group_id,
                    UserGroupMembership.group_id == group_id,
                ),
            ),
        )
        if int(active_users.scalar_one()) > 0:
            raise Conflict(message="Group has active users", details={"id": group_id})

        out = GroupOut.model_validate(group)
        await self._session.delete(group)
        await self._session.commit()
        return out
