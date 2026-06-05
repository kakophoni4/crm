from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.db.models.user import User
from app.modules.departments.schemas import (
    DepartmentCreateRequest,
    DepartmentListResponse,
    DepartmentOut,
    DepartmentUpdateRequest,
)
from app.modules.departments.service import DepartmentService
from app.modules.rbac.permissions import Permission
from app.shared.db import get_db
from app.shared.security.permissions import requires_permission

router = APIRouter(prefix="/api/v1/departments", tags=["departments"])


def _service(db: Annotated[AsyncSession, Depends(get_db)]) -> DepartmentService:
    return DepartmentService(db)


@router.get("", response_model=DepartmentListResponse)
async def list_departments(
    actor: Annotated[User, Depends(requires_permission(Permission.DEPARTMENTS_READ))],
    service: Annotated[DepartmentService, Depends(_service)],
) -> DepartmentListResponse:
    return await service.list_departments(actor)


@router.post("", response_model=DepartmentOut, status_code=201)
async def create_department(
    body: DepartmentCreateRequest,
    actor: Annotated[User, Depends(requires_permission(Permission.DEPARTMENTS_CREATE))],
    service: Annotated[DepartmentService, Depends(_service)],
) -> DepartmentOut:
    return await service.create_department(actor, body)


@router.patch("/{department_id}", response_model=DepartmentOut)
async def update_department(
    department_id: int,
    body: DepartmentUpdateRequest,
    actor: Annotated[User, Depends(requires_permission(Permission.DEPARTMENTS_HEAD_ASSIGN))],
    service: Annotated[DepartmentService, Depends(_service)],
) -> DepartmentOut:
    return await service.update_department(actor, department_id, body)


@router.delete("/{department_id}", response_model=DepartmentOut)
async def delete_department(
    department_id: int,
    actor: Annotated[User, Depends(requires_permission(Permission.DEPARTMENTS_DELETE))],
    service: Annotated[DepartmentService, Depends(_service)],
) -> DepartmentOut:
    return await service.delete_department(actor, department_id)
