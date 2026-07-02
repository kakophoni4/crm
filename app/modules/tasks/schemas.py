from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.tasks.types import TaskType


class TaskCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=512)
    description: str | None = Field(default=None, max_length=5000)
    task_type: TaskType = TaskType.NORMAL
    assignee_id: int = Field(gt=0)
    due_at: datetime | None = None


class TaskUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=512)
    description: str | None = Field(default=None, max_length=5000)
    task_type: TaskType | None = None
    assignee_id: int | None = Field(default=None, gt=0)
    due_at: datetime | None = None


class TaskUserBrief(BaseModel):
    id: int
    full_name: str


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    department_id: int
    title: str
    description: str | None
    task_type: str
    task_type_label: str
    status: str
    created_by: int
    assignee_id: int
    due_at: datetime | None
    completed_at: datetime | None
    completed_by: int | None
    confirmed_at: datetime | None
    confirmed_by: int | None
    created_at: datetime
    updated_at: datetime
    is_overdue: bool = False
    due_soon: bool = False
    creator: TaskUserBrief | None = None
    assignee: TaskUserBrief | None = None


class TaskBoardColumn(BaseModel):
    status: str
    label: str
    items: list[TaskResponse]


class TaskBoardResponse(BaseModel):
    columns: list[TaskBoardColumn]
    task_types: list[dict[str, str | int]]


class TaskListResponse(BaseModel):
    items: list[TaskResponse]
    total: int
