from __future__ import annotations

from enum import StrEnum


class TaskType(StrEnum):
    URGENT = "urgent"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class TaskStatus(StrEnum):
    NEW = "new"
    OPEN = "open"
    DONE_PENDING = "done_pending"
    CLOSED = "closed"


TASK_TYPE_SORT_ORDER: dict[TaskType, int] = {
    TaskType.URGENT: 0,
    TaskType.HIGH: 1,
    TaskType.NORMAL: 2,
    TaskType.LOW: 3,
}

TASK_TYPE_LABELS: dict[TaskType, str] = {
    TaskType.URGENT: "Срочная",
    TaskType.HIGH: "Высокий приоритет",
    TaskType.NORMAL: "Обычная",
    TaskType.LOW: "Низкий приоритет",
}

ACTIVE_TASK_STATUSES = frozenset({TaskStatus.NEW, TaskStatus.OPEN, TaskStatus.DONE_PENDING})
