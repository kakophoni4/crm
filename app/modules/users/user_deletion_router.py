from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.db.models.enums import UserDeletionRequestState
from app.modules.db.models.user import User
from app.modules.rbac.permissions import Permission
from app.modules.users.schemas import (
    UserDeletionRequestListResponse,
    UserDeletionRequestOut,
    UserDeletionRequestRejectBody,
)
from app.modules.users.user_deletion_service import UserDeletionRequestService
from app.shared.db import get_db
from app.shared.security.permissions import requires_permission

router = APIRouter(prefix="/api/v1/user-deletion-requests", tags=["user-deletion-requests"])


def _svc(db: Annotated[AsyncSession, Depends(get_db)]) -> UserDeletionRequestService:
    return UserDeletionRequestService(db)


@router.get("", response_model=UserDeletionRequestListResponse)
async def list_user_deletion_requests(
    actor: Annotated[User, Depends(requires_permission(Permission.USERS_DELETION_REQUEST_READ))],
    service: Annotated[UserDeletionRequestService, Depends(_svc)],
    state: Annotated[UserDeletionRequestState | None, Query()] = None,
) -> UserDeletionRequestListResponse:
    rows = await service.list_requests(actor, state=state)
    return UserDeletionRequestListResponse(
        items=[UserDeletionRequestOut.model_validate(service.to_dict(r)) for r in rows],
    )


@router.post("/{request_id}/approve", response_model=UserDeletionRequestOut)
async def approve_user_deletion_request(
    request_id: int,
    actor: Annotated[User, Depends(requires_permission(Permission.USERS_DELETION_REQUEST_APPROVE))],
    service: Annotated[UserDeletionRequestService, Depends(_svc)],
) -> UserDeletionRequestOut:
    row = await service.approve(actor, request_id)
    return UserDeletionRequestOut.model_validate(service.to_dict(row))


@router.post("/{request_id}/reject", response_model=UserDeletionRequestOut)
async def reject_user_deletion_request(
    request_id: int,
    body: UserDeletionRequestRejectBody,
    actor: Annotated[User, Depends(requires_permission(Permission.USERS_DELETION_REQUEST_REJECT))],
    service: Annotated[UserDeletionRequestService, Depends(_svc)],
) -> UserDeletionRequestOut:
    row = await service.reject(actor, request_id, admin_comment=body.admin_comment)
    return UserDeletionRequestOut.model_validate(service.to_dict(row))
