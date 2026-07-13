from __future__ import annotations

import secrets
import string

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.repository import AuthRepository
from app.modules.contacts.scope_loader import ScopeLoader
from app.modules.db.models.department import Department
from app.modules.db.models.enums import UserRole, UserStatus
from app.modules.db.models.user import User
from app.modules.rbac.scope import SCOPE_ALL, can_act_on_user, visible_user_ids
from app.modules.users.memberships import (
    resolve_group_department_ids,
    set_user_group_memberships,
)
from app.modules.users.repository import UserRepository
from app.modules.users.schemas import (
    ForceLogoutResponse,
    ResetPasswordResponse,
    UserCreateRequest,
    UserListResponse,
    UserOut,
    UserUpdateRequest,
    _normalize_group_ids,
)
from app.modules.users.serialization import user_to_out
from app.shared.exceptions import Conflict, NotFound, PermissionDenied, ValidationError
from app.shared.security.passwords import hash_password


def _generate_temp_password(length: int = 16) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return "".join(secrets.choice(alphabet) for _ in range(length))


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = UserRepository(session)
        self._auth_repo = AuthRepository(session)

    async def _filter_visible(self, actor: User, rows: list[User]) -> list[User]:
        ctx = await ScopeLoader(self._session).load(actor)
        visible = visible_user_ids(ctx)
        if visible == SCOPE_ALL:
            return rows
        assert isinstance(visible, set)
        return [row for row in rows if row.id in visible]

    async def _ensure_can_view(self, actor: User, target: User) -> None:
        ctx = await ScopeLoader(self._session).load(actor)
        if not can_act_on_user(ctx, target):
            raise NotFound(message="User not found", details={"id": target.id})

    def _ensure_can_create_role(self, actor: User, role: UserRole) -> None:
        actor_role = actor.role if isinstance(actor.role, UserRole) else UserRole(str(actor.role))
        if actor_role == UserRole.ADMIN:
            return
        if actor_role in (UserRole.SENIOR, UserRole.GROUP_SENIOR):
            if role != UserRole.USER:
                raise PermissionDenied(message="Managers can only create users with role=user")
            return
        raise PermissionDenied()

    async def _resolve_group(
        self,
        actor: User,
        group_id: int,
    ) -> tuple[int, int]:
        group = await self._repo.get_group(group_id)
        if group is None:
            raise ValidationError(
                message="group_id does not exist",
                details={"group_id": group_id},
            )
        actor_role = actor.role if isinstance(actor.role, UserRole) else UserRole(str(actor.role))
        if actor_role == UserRole.SENIOR and actor.department_id != group.department_id:
            raise PermissionDenied(message="Senior can only assign groups in own department")
        return group.id, group.department_id

    async def _resolve_group_ids(
        self,
        actor: User,
        group_ids: list[int],
    ) -> tuple[list[int], int]:
        if not group_ids:
            raise ValidationError(
                message="At least one group is required",
                details={"field": "group_ids"},
            )
        dept_map = await resolve_group_department_ids(self._session, group_ids)
        missing = [gid for gid in group_ids if gid not in dept_map]
        if missing:
            raise ValidationError(
                message="group_id does not exist",
                details={"group_ids": missing},
            )
        departments = set(dept_map.values())
        if len(departments) != 1:
            raise ValidationError(
                message="All groups must belong to the same department",
                details={"group_ids": group_ids},
            )
        department_id = next(iter(departments))
        actor_role = actor.role if isinstance(actor.role, UserRole) else UserRole(str(actor.role))
        if actor_role == UserRole.SENIOR and actor.department_id != department_id:
            raise PermissionDenied(message="Senior can only assign groups in own department")
        return group_ids, department_id

    async def _resolve_department(self, actor: User, department_id: int) -> int:
        department = await self._session.get(Department, department_id)
        if department is None:
            raise ValidationError(
                message="department_id does not exist",
                details={"department_id": department_id},
            )
        actor_role = actor.role if isinstance(actor.role, UserRole) else UserRole(str(actor.role))
        if actor_role == UserRole.SENIOR and actor.department_id != department_id:
            raise PermissionDenied(message="Senior can only assign own department")
        return department.id

    async def _set_department_head(self, department_id: int, user_id: int) -> None:
        department = await self._session.get(Department, department_id)
        if department is None:
            raise ValidationError(
                message="department_id does not exist",
                details={"department_id": department_id},
            )
        department.head_user_id = user_id
        await self._session.flush()

    async def _clear_department_head_if_user(self, user_id: int) -> None:
        result = await self._session.execute(
            select(Department).where(Department.head_user_id == user_id),
        )
        for department in result.scalars().all():
            department.head_user_id = None
        await self._session.flush()

    async def _ensure_actor_can_assign_groups(
        self,
        actor: User,
        group_ids: list[int],
    ) -> None:
        actor_role = actor.role if isinstance(actor.role, UserRole) else UserRole(str(actor.role))
        if actor_role == UserRole.ADMIN:
            return
        if actor_role == UserRole.SENIOR:
            return
        if actor_role == UserRole.GROUP_SENIOR:
            from app.modules.users.memberships import list_user_group_ids

            allowed = set(await list_user_group_ids(self._session, actor.id))
            extra = [gid for gid in group_ids if gid not in allowed]
            if extra:
                raise PermissionDenied(
                    message="Group senior can only assign users within own groups",
                )
            return
        raise PermissionDenied()

    async def _resolve_create_assignment(
        self,
        actor: User,
        body: UserCreateRequest,
    ) -> tuple[list[int], int | None]:
        role = body.role if isinstance(body.role, UserRole) else UserRole(str(body.role))
        normalized = _normalize_group_ids(body.group_id, body.group_ids)
        if role == UserRole.ADMIN:
            if normalized or body.department_id is not None:
                raise ValidationError(
                    message="Admin must not be assigned to a group or department",
                )
            return [], None
        if role in (UserRole.USER, UserRole.GROUP_SENIOR):
            if not normalized:
                raise ValidationError(
                    message="group_ids is required for this role",
                    details={"field": "group_ids"},
                )
            group_ids, department_id = await self._resolve_group_ids(actor, normalized)
            await self._ensure_actor_can_assign_groups(actor, group_ids)
            return group_ids, department_id
        if role == UserRole.SENIOR:
            if body.department_id is None:
                raise ValidationError(
                    message="department_id is required for senior role",
                    details={"field": "department_id"},
                )
            department_id = await self._resolve_department(actor, body.department_id)
            senior_groups: list[int] = []
            if normalized:
                senior_groups, group_department_id = await self._resolve_group_ids(
                    actor,
                    normalized,
                )
                if group_department_id != department_id:
                    raise ValidationError(
                        message="group must belong to the selected department",
                        details={"group_ids": senior_groups, "department_id": department_id},
                    )
            return senior_groups, department_id
        if role == UserRole.ACCOUNTANT:
            if normalized or body.department_id is not None:
                raise ValidationError(
                    message="Accountant must not be assigned to a group or department",
                )
            return [], None
        raise PermissionDenied()

    async def list_users(
        self,
        actor: User,
        *,
        role: UserRole | None,
        group_id: int | None,
        department_id: int | None,
        q: str | None,
        limit: int,
    ) -> UserListResponse:
        rows = await self._repo.list_users(
            role=role,
            group_id=group_id,
            department_id=department_id,
            q=q,
            limit=limit,
        )
        visible_rows = await self._filter_visible(actor, rows)
        items = [await user_to_out(self._session, row) for row in visible_rows]
        return UserListResponse(items=items)

    async def get_user(self, actor: User, user_id: int) -> UserOut:
        target = await self._repo.get_by_id(user_id)
        if target is None:
            raise NotFound(message="User not found", details={"id": user_id})
        await self._ensure_can_view(actor, target)
        return await user_to_out(self._session, target)

    async def create_user(self, actor: User, body: UserCreateRequest) -> UserOut:
        self._ensure_can_create_role(actor, body.role)
        group_ids, department_id = await self._resolve_create_assignment(actor, body)

        email = (body.email.strip().lower() if body.email else f"{body.username}@crm.local")
        user = User(
            email=email,
            username=body.username.strip().lower(),
            password_hash=hash_password(body.password),
            full_name=body.full_name.strip(),
            role=body.role,
            group_id=group_ids[0] if len(group_ids) == 1 else None,
            department_id=department_id,
            status=UserStatus.ACTIVE,
            created_by=actor.id,
        )
        try:
            created = await self._repo.add(user)
            if group_ids:
                await set_user_group_memberships(self._session, created.id, group_ids)
            if body.set_as_department_head:
                if department_id is None:
                    raise ValidationError(
                        message="set_as_department_head requires department assignment",
                    )
                role = (
                    body.role if isinstance(body.role, UserRole) else UserRole(str(body.role))
                )
                if role != UserRole.SENIOR:
                    raise ValidationError(
                        message="Only senior can be assigned as department head",
                    )
                await self._set_department_head(department_id, created.id)
            await self._repo.commit()
        except IntegrityError as exc:
            await self._repo.rollback()
            raise Conflict(message="User email or username already exists") from exc
        return await user_to_out(self._session, created)

    async def update_user(
        self,
        actor: User,
        user_id: int,
        body: UserUpdateRequest,
    ) -> UserOut:
        target = await self._repo.get_by_id(user_id)
        if target is None:
            raise NotFound(message="User not found", details={"id": user_id})
        await self._ensure_can_view(actor, target)

        actor_role = actor.role if isinstance(actor.role, UserRole) else UserRole(str(actor.role))
        previous_role = (
            target.role if isinstance(target.role, UserRole) else UserRole(str(target.role))
        )
        normalized_groups = _normalize_group_ids(body.group_id, body.group_ids)
        if actor_role != UserRole.ADMIN:
            if previous_role == UserRole.SENIOR:
                raise PermissionDenied(message="Cannot modify senior user")
            if body.role is not None:
                # Старшие могут только переключать оператор ↔ старший группы.
                toggle_ok = actor_role in (UserRole.SENIOR, UserRole.GROUP_SENIOR) and {
                    previous_role,
                    body.role,
                } == {UserRole.USER, UserRole.GROUP_SENIOR}
                if not toggle_ok:
                    raise PermissionDenied()
            if (
                normalized_groups is not None
                and target.department_id != actor.department_id
            ):
                raise PermissionDenied()

        try:
            if body.full_name is not None:
                target.full_name = body.full_name.strip()
            if body.status is not None:
                target.status = body.status
            if body.availability is not None:
                target.availability = body.availability
            if body.role is not None:
                if actor_role == UserRole.ADMIN:
                    self._ensure_can_create_role(actor, body.role)
                target.role = body.role
                if body.role in (UserRole.ADMIN, UserRole.ACCOUNTANT):
                    target.group_id = None
                    target.department_id = None
                    await set_user_group_memberships(self._session, target.id, [])
                elif body.role == UserRole.SENIOR:
                    if body.department_id is None and target.department_id is None:
                        raise ValidationError(
                            message="department_id is required when role is senior",
                            details={"field": "department_id"},
                        )
                    # Старший отдела не обязан состоять в группах оператора.
                    if normalized_groups is None:
                        target.group_id = None
                        await set_user_group_memberships(self._session, target.id, [])
                elif body.role in (UserRole.USER, UserRole.GROUP_SENIOR):
                    # Группы не трогаем при повышении/понижении — остаются как были.
                    if normalized_groups is None and not await self._user_has_groups(target.id):
                        raise ValidationError(
                            message="group_ids is required for this role",
                            details={"field": "group_ids"},
                        )

            effective_role = (
                target.role if isinstance(target.role, UserRole) else UserRole(str(target.role))
            )

            if body.department_id is not None:
                if actor_role != UserRole.ADMIN:
                    raise PermissionDenied()
                if effective_role != UserRole.SENIOR:
                    raise ValidationError(
                        message="department_id applies only to senior role",
                        details={"field": "department_id"},
                    )
                target.department_id = await self._resolve_department(actor, body.department_id)
                if normalized_groups is None and body.group_id is None and body.group_ids is None:
                    target.group_id = None
                    await set_user_group_memberships(self._session, target.id, [])

            if normalized_groups is not None:
                if effective_role in (UserRole.USER, UserRole.GROUP_SENIOR):
                    if not normalized_groups:
                        raise ValidationError(
                            message="At least one group is required",
                            details={"field": "group_ids"},
                        )
                    group_ids, department_id = await self._resolve_group_ids(
                        actor,
                        normalized_groups,
                    )
                    await self._ensure_actor_can_assign_groups(actor, group_ids)
                    target.department_id = department_id
                    await set_user_group_memberships(self._session, target.id, group_ids)
                elif effective_role == UserRole.SENIOR:
                    if not normalized_groups:
                        target.group_id = None
                        await set_user_group_memberships(self._session, target.id, [])
                    else:
                        group_ids, group_department_id = await self._resolve_group_ids(
                            actor,
                            normalized_groups,
                        )
                        if (
                            target.department_id is not None
                            and group_department_id != target.department_id
                        ):
                            raise ValidationError(
                                message="group must belong to the selected department",
                            )
                        await set_user_group_memberships(self._session, target.id, group_ids)
                else:
                    await set_user_group_memberships(self._session, target.id, [])

            if body.set_as_department_head:
                if effective_role != UserRole.SENIOR or target.department_id is None:
                    raise ValidationError(
                        message="Only senior with department can be department head",
                    )
                await self._set_department_head(target.department_id, target.id)

            if previous_role == UserRole.SENIOR and effective_role != UserRole.SENIOR:
                await self._clear_department_head_if_user(target.id)

            await self._session.flush()
            await self._repo.commit()
        except IntegrityError as exc:
            await self._repo.rollback()
            raise Conflict(message="Failed to update user due to data conflict") from exc

        await self._session.refresh(target)
        return await user_to_out(self._session, target)

    async def _user_has_groups(self, user_id: int) -> bool:
        from app.modules.users.memberships import list_user_group_ids

        return bool(await list_user_group_ids(self._session, user_id))

    async def reset_password(self, actor: User, user_id: int) -> ResetPasswordResponse:
        target = await self._repo.get_by_id(user_id)
        if target is None:
            raise NotFound(message="User not found", details={"id": user_id})
        await self._ensure_can_view(actor, target)

        temp = _generate_temp_password()
        target.password_hash = hash_password(temp)
        await self._session.flush()
        await self._repo.commit()
        return ResetPasswordResponse(temporary_password=temp)

    async def force_logout(self, actor: User, user_id: int) -> ForceLogoutResponse:
        target = await self._repo.get_by_id(user_id)
        if target is None:
            raise NotFound(message="User not found", details={"id": user_id})
        await self._ensure_can_view(actor, target)
        await self._auth_repo.revoke_all_refresh_tokens_for_user(user_id)
        await self._repo.commit()
        return ForceLogoutResponse()
