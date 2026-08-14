from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.db.models.user import User
from app.modules.rbac.permissions import Permission
from app.modules.tasks.schemas import (
    ClientRequirementCreateRequest,
    ClientRequirementUnitListResponse,
    TaskAlertsResponse,
    TaskAssigneeListResponse,
    TaskBoardResponse,
    TaskCommentCreateRequest,
    TaskCommentListResponse,
    TaskCommentResponse,
    TaskCreateRequest,
    TaskDetailResponse,
    TaskListResponse,
    TaskMoveRequest,
    TaskNotifyRequest,
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


@router.get("/alerts", response_model=TaskAlertsResponse)
async def task_alerts(
    actor: Annotated[User, Depends(requires_permission(Permission.TASKS_READ))],
    service: Annotated[TaskService, Depends(_service)],
) -> TaskAlertsResponse:
    return await service.alerts(actor)


@router.get("/assignees", response_model=TaskAssigneeListResponse)
async def list_task_assignees(
    actor: Annotated[User, Depends(requires_permission(Permission.TASKS_READ))],
    service: Annotated[TaskService, Depends(_service)],
) -> TaskAssigneeListResponse:
    return await service.list_assignees(actor)


@router.get("/client-requirement-units", response_model=ClientRequirementUnitListResponse)
async def list_client_requirement_units(
    actor: Annotated[User, Depends(requires_permission(Permission.TASKS_READ))],
    service: Annotated[TaskService, Depends(_service)],
) -> ClientRequirementUnitListResponse:
    return await service.list_client_requirement_units(actor)


@router.post("/client-requirements", status_code=201, response_model=TaskResponse)
async def create_client_requirement(
    body: ClientRequirementCreateRequest,
    actor: Annotated[User, Depends(requires_permission(Permission.TASKS_READ))],
    service: Annotated[TaskService, Depends(_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TaskResponse:
    result = await service.create_client_requirement(actor, body)
    await db.commit()
    return result


@router.get("/by-chat/{chat_id}", response_model=TaskListResponse)
async def list_client_requirements_by_chat(
    chat_id: int,
    actor: Annotated[User, Depends(requires_permission(Permission.TASKS_READ))],
    service: Annotated[TaskService, Depends(_service)],
) -> TaskListResponse:
    return await service.list_for_chat(actor, chat_id)


@router.post("/{task_id}/acknowledge", response_model=TaskResponse)
async def acknowledge_task(
    task_id: int,
    actor: Annotated[User, Depends(requires_permission(Permission.TASKS_READ))],
    service: Annotated[TaskService, Depends(_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TaskResponse:
    result = await service.acknowledge(actor, task_id)
    await db.commit()
    return result


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
    actor: Annotated[User, Depends(requires_permission(Permission.TASKS_READ))],
    service: Annotated[TaskService, Depends(_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TaskResponse:
    result = await service.create(actor, body)
    await db.commit()
    return result


@router.get("/{task_id}", response_model=TaskDetailResponse)
async def get_task(
    task_id: int,
    actor: Annotated[User, Depends(requires_permission(Permission.TASKS_READ))],
    service: Annotated[TaskService, Depends(_service)],
) -> TaskDetailResponse:
    return await service.get_task(actor, task_id)


@router.get("/{task_id}/comments", response_model=TaskCommentListResponse)
async def list_task_comments(
    task_id: int,
    actor: Annotated[User, Depends(requires_permission(Permission.TASKS_READ))],
    service: Annotated[TaskService, Depends(_service)],
) -> TaskCommentListResponse:
    return await service.list_comments(actor, task_id)


@router.post("/{task_id}/comments", status_code=201, response_model=TaskCommentResponse)
async def add_task_comment(
    task_id: int,
    body: TaskCommentCreateRequest,
    actor: Annotated[User, Depends(requires_permission(Permission.TASKS_READ))],
    service: Annotated[TaskService, Depends(_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TaskCommentResponse:
    result = await service.add_comment(actor, task_id, body.body)
    await db.commit()
    return result


@router.post("/{task_id}/notify-assignee")
async def notify_task_assignee(
    task_id: int,
    body: TaskNotifyRequest,
    actor: Annotated[User, Depends(requires_permission(Permission.TASKS_READ))],
    service: Annotated[TaskService, Depends(_service)],
) -> dict[str, bool]:
    return await service.notify_assignee(actor, task_id, body.message)


@router.post("/{task_id}/notify-creator")
async def notify_task_creator(
    task_id: int,
    body: TaskNotifyRequest,
    actor: Annotated[User, Depends(requires_permission(Permission.TASKS_READ))],
    service: Annotated[TaskService, Depends(_service)],
) -> dict[str, bool]:
    return await service.notify_creator(actor, task_id, body.message)


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
