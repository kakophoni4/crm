from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.contacts.scope_loader import ScopeLoader
from app.modules.db.models.department import Department
from app.modules.db.models.enums import UserRole
from app.modules.db.models.user import User
from app.modules.departments.repository import DepartmentRepository
from app.modules.departments.schemas import (
    DepartmentCreateRequest,
    DepartmentListResponse,
    DepartmentOut,
    DepartmentUpdateRequest,
)
from app.modules.rbac.scope import SCOPE_ALL, visible_department_ids
from app.shared.exceptions import Conflict, NotFound, PermissionDenied, ValidationError


class DepartmentService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = DepartmentRepository(session)

    async def _visible_ids(self, actor: User) -> set[int] | str:
        ctx = await ScopeLoader(self._session).load(actor)
        return visible_department_ids(ctx)

    def _ensure_visible(self, actor: User, department_id: int, visible: set[int] | str) -> None:
        if visible == SCOPE_ALL:
            return
        if not isinstance(visible, set) or department_id not in visible:
            raise NotFound(message="Department not found", details={"id": department_id})

    async def list_departments(self, actor: User) -> DepartmentListResponse:
        visible = await self._visible_ids(actor)
        rows = await self._repo.list_all()
        if visible != SCOPE_ALL:
            assert isinstance(visible, set)
            rows = [row for row in rows if row.id in visible]
        return DepartmentListResponse(items=[DepartmentOut.model_validate(row) for row in rows])

    async def create_department(
        self,
        actor: User,
        body: DepartmentCreateRequest,
    ) -> DepartmentOut:
        role = actor.role if isinstance(actor.role, UserRole) else UserRole(str(actor.role))
        if role != UserRole.ADMIN:
            raise PermissionDenied()

        if body.head_user_id is not None:
            head = await self._session.get(User, body.head_user_id)
            if head is None:
                raise ValidationError(
                    message="head_user_id does not exist",
                    details={"head_user_id": body.head_user_id},
                )

        department = Department(
            name=body.name.strip(),
            head_user_id=body.head_user_id,
            created_by=actor.id,
        )
        try:
            created = await self._repo.add(department)
            await self._repo.commit()
        except IntegrityError as exc:
            await self._repo.rollback()
            raise Conflict(message="Department name already exists") from exc
        return DepartmentOut.model_validate(created)

    async def update_department(
        self,
        actor: User,
        department_id: int,
        body: DepartmentUpdateRequest,
    ) -> DepartmentOut:
        role = actor.role if isinstance(actor.role, UserRole) else UserRole(str(actor.role))
        if role != UserRole.ADMIN:
            raise PermissionDenied()

        department = await self._repo.get_by_id(department_id)
        if department is None:
            raise NotFound(message="Department not found", details={"id": department_id})

        if body.name is not None:
            department.name = body.name.strip()
        if body.head_user_id is not None:
            head = await self._session.get(User, body.head_user_id)
            if head is None:
                raise ValidationError(
                    message="head_user_id does not exist",
                    details={"head_user_id": body.head_user_id},
                )
            department.head_user_id = body.head_user_id

        try:
            await self._session.flush()
            await self._repo.commit()
            await self._session.refresh(department)
        except IntegrityError as exc:
            await self._repo.rollback()
            raise Conflict(message="Department name already exists") from exc
        return DepartmentOut.model_validate(department)

    async def delete_department(self, actor: User, department_id: int) -> DepartmentOut:
        role = actor.role if isinstance(actor.role, UserRole) else UserRole(str(actor.role))
        if role != UserRole.ADMIN:
            raise PermissionDenied()

        department = await self._repo.get_by_id(department_id)
        if department is None:
            raise NotFound(message="Department not found", details={"id": department_id})

        if await self._repo.count_groups(department_id) > 0:
            raise Conflict(
                message="Department has groups",
                details={"id": department_id},
            )
        if await self._repo.count_users(department_id) > 0:
            raise Conflict(
                message="Department has users",
                details={"id": department_id},
            )

        out = DepartmentOut.model_validate(department)
        await self._session.delete(department)
        await self._repo.commit()
        return out
