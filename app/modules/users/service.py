from __future__ import annotations

import secrets
import string

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.repository import AuthRepository
from app.modules.contacts.scope_loader import ScopeLoader
from app.modules.db.models.enums import UserRole, UserStatus
from app.modules.db.models.user import User
from app.modules.rbac.scope import SCOPE_ALL, can_act_on_user, visible_user_ids
from app.modules.users.repository import UserRepository
from app.modules.users.schemas import (
    ForceLogoutResponse,
    ResetPasswordResponse,
    UserCreateRequest,
    UserListResponse,
    UserOut,
    UserUpdateRequest,
)
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
        if actor_role == UserRole.SENIOR:
            if role != UserRole.USER:
                raise PermissionDenied(message="Senior can only create users with role=user")
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
        return UserListResponse(items=[UserOut.model_validate(row) for row in visible_rows])

    async def get_user(self, actor: User, user_id: int) -> UserOut:
        target = await self._repo.get_by_id(user_id)
        if target is None:
            raise NotFound(message="User not found", details={"id": user_id})
        await self._ensure_can_view(actor, target)
        return UserOut.model_validate(target)

    async def create_user(self, actor: User, body: UserCreateRequest) -> UserOut:
        self._ensure_can_create_role(actor, body.role)
        group_id, department_id = await self._resolve_group(actor, body.group_id)

        email = (body.email.strip().lower() if body.email else f"{body.username}@crm.local")
        user = User(
            email=email,
            username=body.username.strip().lower(),
            password_hash=hash_password(body.password),
            full_name=body.full_name.strip(),
            role=body.role,
            group_id=group_id,
            department_id=department_id,
            status=UserStatus.ACTIVE,
            created_by=actor.id,
        )
        try:
            created = await self._repo.add(user)
            await self._repo.commit()
        except IntegrityError as exc:
            await self._repo.rollback()
            raise Conflict(message="User email or username already exists") from exc
        return UserOut.model_validate(created)

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
        if actor_role != UserRole.ADMIN:
            if body.role is not None or (
                body.group_id is not None
                and target.department_id != actor.department_id
            ):
                raise PermissionDenied()
            target_role = (
                target.role if isinstance(target.role, UserRole) else UserRole(str(target.role))
            )
            if target_role == UserRole.SENIOR:
                raise PermissionDenied(message="Cannot modify senior user")

        if body.full_name is not None:
            target.full_name = body.full_name.strip()
        if body.status is not None:
            target.status = body.status
        if body.availability is not None:
            target.availability = body.availability
        if body.role is not None:
            self._ensure_can_create_role(actor, body.role)
            target.role = body.role
        if body.group_id is not None:
            group_id, department_id = await self._resolve_group(actor, body.group_id)
            target.group_id = group_id
            if actor_role == UserRole.ADMIN:
                target.department_id = department_id

        await self._session.flush()
        await self._repo.commit()
        await self._session.refresh(target)
        return UserOut.model_validate(target)

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
