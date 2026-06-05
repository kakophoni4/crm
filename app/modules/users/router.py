from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.db.models.enums import UserRole
from app.modules.db.models.user import User
from app.modules.rbac.permissions import Permission
from app.modules.users.schemas import (
    ForceLogoutResponse,
    ResetPasswordResponse,
    UserCreateRequest,
    UserDeletionRequestCreateBody,
    UserDeletionRequestOut,
    UserListResponse,
    UserOut,
    UserUpdateRequest,
)
from app.modules.users.service import UserService
from app.modules.users.user_deletion_service import UserDeletionRequestService
from app.shared.db import get_db
from app.shared.security.permissions import requires_permission

router = APIRouter(prefix="/api/v1/users", tags=["users"])


def _service(db: Annotated[AsyncSession, Depends(get_db)]) -> UserService:
    return UserService(db)


def _deletion_service(db: Annotated[AsyncSession, Depends(get_db)]) -> UserDeletionRequestService:
    return UserDeletionRequestService(db)


@router.get("", response_model=UserListResponse)
async def list_users(
    actor: Annotated[User, Depends(requires_permission(Permission.USERS_READ))],
    service: Annotated[UserService, Depends(_service)],
    role: Annotated[UserRole | None, Query()] = None,
    group_id: Annotated[int | None, Query()] = None,
    department_id: Annotated[int | None, Query()] = None,
    q: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> UserListResponse:
    return await service.list_users(
        actor,
        role=role,
        group_id=group_id,
        department_id=department_id,
        q=q,
        limit=limit,
    )


@router.get("/{user_id}", response_model=UserOut)
async def get_user(
    user_id: int,
    actor: Annotated[User, Depends(requires_permission(Permission.USERS_READ))],
    service: Annotated[UserService, Depends(_service)],
) -> UserOut:
    return await service.get_user(actor, user_id)


@router.post("", response_model=UserOut, status_code=201)
async def create_user(
    body: UserCreateRequest,
    actor: Annotated[
        User,
        Depends(
            requires_permission(
                Permission.USERS_CREATE,
                Permission.USERS_CREATE_IN_DEP,
            ),
        ),
    ],
    service: Annotated[UserService, Depends(_service)],
) -> UserOut:
    return await service.create_user(actor, body)


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: int,
    body: UserUpdateRequest,
    actor: Annotated[User, Depends(requires_permission(Permission.USERS_UPDATE))],
    service: Annotated[UserService, Depends(_service)],
) -> UserOut:
    return await service.update_user(actor, user_id, body)


@router.post("/{user_id}/reset-password", response_model=ResetPasswordResponse)
async def reset_password(
    user_id: int,
    actor: Annotated[User, Depends(requires_permission(Permission.USERS_PASSWORD_RESET))],
    service: Annotated[UserService, Depends(_service)],
) -> ResetPasswordResponse:
    return await service.reset_password(actor, user_id)


@router.post("/{user_id}/force-logout", response_model=ForceLogoutResponse)
async def force_logout(
    user_id: int,
    actor: Annotated[User, Depends(requires_permission(Permission.USERS_FORCE_LOGOUT))],
    service: Annotated[UserService, Depends(_service)],
) -> ForceLogoutResponse:
    return await service.force_logout(actor, user_id)


@router.post("/{user_id}/remove", response_model=UserOut)
async def admin_remove_user(
    user_id: int,
    actor: Annotated[User, Depends(requires_permission(Permission.USERS_DEACTIVATE))],
    deletion_service: Annotated[UserDeletionRequestService, Depends(_deletion_service)],
) -> UserOut:
    removed = await deletion_service.admin_remove_user(actor, user_id)
    return UserOut.model_validate(removed)


@router.post(
    "/{user_id}/deletion-request",
    response_model=UserDeletionRequestOut,
    status_code=201,
)
async def create_user_deletion_request(
    user_id: int,
    body: UserDeletionRequestCreateBody,
    actor: Annotated[
        User,
        Depends(requires_permission(Permission.USERS_DELETION_REQUEST_CREATE)),
    ],
    deletion_service: Annotated[UserDeletionRequestService, Depends(_deletion_service)],
) -> UserDeletionRequestOut:
    row = await deletion_service.create_request(actor, user_id, comment=body.comment)
    return UserDeletionRequestOut.model_validate(deletion_service.to_dict(row))
