from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.db.models.department_task import DepartmentTask
from app.modules.db.models.department_task_collaborator import DepartmentTaskCollaborator
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
        # updated_at is TIMESTAMP WITHOUT TIME ZONE — asyncpg rejects aware datetimes.
        row.updated_at = datetime.now(UTC).replace(tzinfo=None)
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
        result = await self._session.execute(
            stmt.order_by(DepartmentTask.position.asc(), DepartmentTask.id.desc()),
        )
        return list(result.scalars().all())

    async def list_closed_for_departments(
        self,
        department_ids: list[int] | None,
        *,
        limit: int = 50,
    ) -> list[DepartmentTask]:
        stmt = select(DepartmentTask).where(DepartmentTask.status == TaskStatus.CLOSED.value)
        if department_ids is not None:
            if not department_ids:
                return []
            stmt = stmt.where(DepartmentTask.department_id.in_(department_ids))
        result = await self._session.execute(
            stmt.order_by(
                DepartmentTask.confirmed_at.desc().nullslast(),
                DepartmentTask.id.desc(),
            ).limit(limit),
        )
        return list(result.scalars().all())

    async def reorder_column(
        self,
        moved: DepartmentTask,
        *,
        status: str,
        position: int,
    ) -> None:
        result = await self._session.execute(
            select(DepartmentTask)
            .where(
                DepartmentTask.department_id == moved.department_id,
                DepartmentTask.status == status,
                DepartmentTask.id != moved.id,
            )
            .order_by(DepartmentTask.position.asc(), DepartmentTask.id.desc()),
        )
        siblings = list(result.scalars().all())
        index = max(0, min(position, len(siblings)))
        siblings.insert(index, moved)
        for pos, row in enumerate(siblings):
            row.position = pos

    async def list_for_assignee(self, assignee_id: int) -> list[DepartmentTask]:
        collab_ids = select(DepartmentTaskCollaborator.task_id).where(
            DepartmentTaskCollaborator.user_id == assignee_id,
        )
        result = await self._session.execute(
            select(DepartmentTask)
            .where(
                self._active_filter(),
                or_(
                    DepartmentTask.assignee_id == assignee_id,
                    DepartmentTask.created_by == assignee_id,
                    DepartmentTask.id.in_(collab_ids),
                ),
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
            try:
                type_order = TASK_TYPE_SORT_ORDER.get(TaskType(row.task_type), 99)
            except ValueError:
                type_order = 99
            due_ts = row.due_at.timestamp() if row.due_at else float("inf")
            return (type_order, due_ts, -row.id)

        return sorted(tasks, key=sort_key)
