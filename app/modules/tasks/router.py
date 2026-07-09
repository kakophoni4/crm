from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.db.models.user import User
from app.modules.rbac.permissions import Permission
from app.modules.tasks.schemas import (
    TaskBoardResponse,
    TaskCreateRequest,
    TaskListResponse,
    TaskMoveRequest,
    TaskResponse,
    TaskUpdateRequest,
)
from app.modules.tasks.service import TaskService
from app.shared.db import get_db
from app.shared.security.permissions import requires_permission

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


def _service(db: Annotated[AsyncSession, Depends(get_db)]) -> TaskService:
    return TaskService(db)


@router.get("/mine", response_model=TaskListResponse)
async def list_my_tasks(
    actor: Annotated[User, Depends(requires_permission(Permission.TASKS_READ))],
    service: Annotated[TaskService, Depends(_service)],
) -> TaskListResponse:
    return await service.list_my_tasks(actor)


@router.get("/board", response_model=TaskBoardResponse)
async def task_board(
    actor: Annotated[User, Depends(requires_permission(Permission.TASKS_MANAGE))],
    service: Annotated[TaskService, Depends(_service)],
    department_id: Annotated[int | None, Query()] = None,
) -> TaskBoardResponse:
    return await service.board(actor, department_id=department_id)


@router.post("", status_code=201, response_model=TaskResponse)
async def create_task(
    body: TaskCreateRequest,
    actor: Annotated[User, Depends(requires_permission(Permission.TASKS_MANAGE))],
    service: Annotated[TaskService, Depends(_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TaskResponse:
    result = await service.create(actor, body)
    await db.commit()
    return result


@router.patch("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: int,
    body: TaskUpdateRequest,
    actor: Annotated[User, Depends(requires_permission(Permission.TASKS_MANAGE))],
    service: Annotated[TaskService, Depends(_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TaskResponse:
    result = await service.update(actor, task_id, body)
    await db.commit()
    return result


@router.post("/{task_id}/move", response_model=TaskResponse)
async def move_task(
    task_id: int,
    body: TaskMoveRequest,
    actor: Annotated[User, Depends(requires_permission(Permission.TASKS_MANAGE))],
    service: Annotated[TaskService, Depends(_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TaskResponse:
    result = await service.move(actor, task_id, body)
    await db.commit()
    return result


@router.post("/{task_id}/complete", response_model=TaskResponse)
async def complete_task(
    task_id: int,
    actor: Annotated[User, Depends(requires_permission(Permission.TASKS_READ))],
    service: Annotated[TaskService, Depends(_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TaskResponse:
    result = await service.complete(actor, task_id)
    await db.commit()
    return result


@router.post("/{task_id}/confirm", response_model=TaskResponse)
async def confirm_task(
    task_id: int,
    actor: Annotated[User, Depends(requires_permission(Permission.TASKS_MANAGE))],
    service: Annotated[TaskService, Depends(_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TaskResponse:
    result = await service.confirm(actor, task_id)
    await db.commit()
    return result


@router.post("/{task_id}/reopen", response_model=TaskResponse)
async def reopen_task(
    task_id: int,
    actor: Annotated[User, Depends(requires_permission(Permission.TASKS_MANAGE))],
    service: Annotated[TaskService, Depends(_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TaskResponse:
    result = await service.reopen(actor, task_id)
    await db.commit()
    return result


@router.delete("/{task_id}")
async def delete_task(
    task_id: int,
    actor: Annotated[User, Depends(requires_permission(Permission.TASKS_MANAGE))],
    service: Annotated[TaskService, Depends(_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, bool]:
    await service.delete(actor, task_id)
    await db.commit()
    return {"deleted": True}
