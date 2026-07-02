from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.db.models.department_task import DepartmentTask
from app.modules.tasks.types import ACTIVE_TASK_STATUSES, TASK_TYPE_SORT_ORDER, TaskStatus, TaskType


class TaskRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, task_id: int) -> DepartmentTask | None:
        return await self._session.get(DepartmentTask, task_id)

    async def create(self, row: DepartmentTask) -> DepartmentTask:
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return row

    async def save(self, row: DepartmentTask) -> DepartmentTask:
        row.updated_at = datetime.now(UTC)
        await self._session.flush()
        await self._session.refresh(row)
        return row

    def _active_filter(self):
        return DepartmentTask.status.in_([s.value for s in ACTIVE_TASK_STATUSES])

    async def list_for_department(
        self,
        department_id: int,
    ) -> list[DepartmentTask]:
        return await self.list_for_departments([department_id])

    async def list_for_departments(
        self,
        department_ids: list[int] | None,
    ) -> list[DepartmentTask]:
        stmt = select(DepartmentTask).where(self._active_filter())
        if department_ids is not None:
            if not department_ids:
                return []
            stmt = stmt.where(DepartmentTask.department_id.in_(department_ids))
        result = await self._session.execute(stmt.order_by(DepartmentTask.created_at.desc()))
        return list(result.scalars().all())

    async def list_for_assignee(self, assignee_id: int) -> list[DepartmentTask]:
        result = await self._session.execute(
            select(DepartmentTask)
            .where(
                DepartmentTask.assignee_id == assignee_id,
                self._active_filter(),
            )
            .order_by(DepartmentTask.created_at.desc()),
        )
        return list(result.scalars().all())

    async def list_due_for_reminder(
        self,
        *,
        now: datetime,
        within: timedelta,
    ) -> list[DepartmentTask]:
        deadline = now + within
        result = await self._session.execute(
            select(DepartmentTask).where(
                DepartmentTask.status == TaskStatus.OPEN.value,
                DepartmentTask.due_at.is_not(None),
                DepartmentTask.due_at <= deadline,
                DepartmentTask.due_at > now,
                DepartmentTask.due_reminder_sent_at.is_(None),
            ),
        )
        return list(result.scalars().all())

    async def mark_reminder_sent(self, task_id: int, at: datetime) -> None:
        await self._session.execute(
            update(DepartmentTask)
            .where(DepartmentTask.id == task_id)
            .values(due_reminder_sent_at=at),
        )

    @staticmethod
    def sort_tasks_for_assignee(tasks: list[DepartmentTask]) -> list[DepartmentTask]:
        def sort_key(row: DepartmentTask) -> tuple[int, float, int]:
            type_order = TASK_TYPE_SORT_ORDER.get(TaskType(row.task_type), 99)
            due_ts = row.due_at.timestamp() if row.due_at else float("inf")
            return (type_order, due_ts, -row.id)

        return sorted(tasks, key=sort_key)
