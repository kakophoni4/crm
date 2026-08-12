from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.tasks.types import TaskStatus, TaskType


class TaskCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=512)
    description: str | None = Field(default=None, max_length=5000)
    task_type: TaskType = TaskType.NORMAL
    assignee_id: int = Field(gt=0)
    department_id: int | None = Field(default=None, gt=0)
    due_at: datetime | None = None


class TaskUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=512)
    description: str | None = Field(default=None, max_length=5000)
    task_type: TaskType | None = None
    assignee_id: int | None = Field(default=None, gt=0)
    due_at: datetime | None = None


class TaskMoveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: TaskStatus
    position: int = Field(default=0, ge=0)


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
    source: str = "manual"
    opt_unit_id: int | None = None
    opt_requirement_id: int | None = None
    chat_id: int | None = None
    lead_id: int | None = None
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
    needs_ack: bool = False
    creator: TaskUserBrief | None = None
    assignee: TaskUserBrief | None = None
    file_ids: list[int] = Field(default_factory=list)
    files: list["TaskFileBrief"] = Field(default_factory=list)


class TaskFileBrief(BaseModel):
    id: int
    original_name: str
    mime_type: str
    size_bytes: int


class TaskCommentCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str = Field(min_length=1, max_length=5000)


class TaskCommentResponse(BaseModel):
    id: int
    task_id: int
    author_id: int
    body: str
    created_at: datetime
    author: TaskUserBrief | None = None


class TaskCommentListResponse(BaseModel):
    items: list[TaskCommentResponse]


class TaskNotifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str | None = Field(default=None, max_length=1000)


class TaskDetailResponse(TaskResponse):
    comments: list[TaskCommentResponse] = Field(default_factory=list)


class ClientRequirementCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    unit_id: int = Field(gt=0)
    # Optional: if omitted, falls back to accountant bound to the unit.
    assignee_id: int | None = Field(default=None, gt=0)
    title: str = Field(min_length=1, max_length=512)
    description: str | None = Field(default=None, max_length=5000)
    due_at: datetime | None = None
    file_ids: list[int] = Field(default_factory=list)
    chat_id: int | None = Field(default=None, gt=0)
    lead_id: int | None = Field(default=None, gt=0)


class TaskAlertsResponse(BaseModel):
    blink: bool = False
    due_soon: int = 0
    overdue: int = 0
    unacked_fns: int = 0
    client_due: int = 0


class ClientRequirementUnitOption(BaseModel):
    id: int
    inn: str
    name: str
    accountant_user_id: int | None = None


class TaskAssigneeOption(BaseModel):
    id: int
    full_name: str
    role: str = ""
    department_id: int | None = None


class TaskAssigneeListResponse(BaseModel):
    items: list[TaskAssigneeOption]


class ClientRequirementAccountantOption(BaseModel):
    id: int
    full_name: str
    role: str = ""


class ClientRequirementUnitListResponse(BaseModel):
    items: list[ClientRequirementUnitOption]
    accountants: list[ClientRequirementAccountantOption] = Field(default_factory=list)
    assignees: list[ClientRequirementAccountantOption] = Field(default_factory=list)


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
