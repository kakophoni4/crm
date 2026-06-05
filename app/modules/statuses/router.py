from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.db.models.enums import StatusKind
from app.modules.db.models.user import User
from app.modules.rbac.permissions import Permission
from app.modules.statuses.schemas import (
    StatusCreateRequest,
    StatusListResponse,
    StatusOut,
    StatusUpdateRequest,
)
from app.modules.statuses.service import StatusService
from app.shared.db import get_db
from app.shared.security.permissions import requires_permission

router = APIRouter(prefix="/api/v1/statuses", tags=["statuses"])


def _service(db: Annotated[AsyncSession, Depends(get_db)]) -> StatusService:
    return StatusService(db)


@router.get("", response_model=StatusListResponse)
async def list_statuses(
    _actor: Annotated[User, Depends(requires_permission(Permission.STATUSES_READ))],
    service: Annotated[StatusService, Depends(_service)],
    include_inactive: bool = Query(default=False),
    kind: Annotated[StatusKind | None, Query()] = None,
) -> StatusListResponse:
    return await service.list_statuses(include_inactive=include_inactive, kind=kind)


@router.post("", response_model=StatusOut, status_code=201)
async def create_status(
    body: StatusCreateRequest,
    _actor: Annotated[User, Depends(requires_permission(Permission.STATUSES_MANAGE))],
    service: Annotated[StatusService, Depends(_service)],
) -> StatusOut:
    return await service.create_status(body)


@router.patch("/{status_id}", response_model=StatusOut)
async def update_status(
    status_id: int,
    body: StatusUpdateRequest,
    _actor: Annotated[User, Depends(requires_permission(Permission.STATUSES_MANAGE))],
    service: Annotated[StatusService, Depends(_service)],
) -> StatusOut:
    return await service.update_status(status_id, body)


@router.delete("/{status_id}", response_model=StatusOut)
async def delete_status(
    status_id: int,
    _actor: Annotated[User, Depends(requires_permission(Permission.STATUSES_MANAGE))],
    service: Annotated[StatusService, Depends(_service)],
) -> StatusOut:
    return await service.delete_status(status_id)
