from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.contacts.scope_loader import ScopeLoader
from app.modules.db.models.department_task import DepartmentTask
from app.modules.db.models.enums import UserRole
from app.modules.db.models.user import User
from app.modules.rbac.scope import SCOPE_ALL, ScopeContext, can_act_on_user, visible_department_ids
from app.modules.tasks.repository import TaskRepository
from app.modules.tasks.schemas import (
    TaskBoardColumn,
    TaskBoardResponse,
    TaskCreateRequest,
    TaskListResponse,
    TaskMoveRequest,
    TaskResponse,
    TaskUpdateRequest,
    TaskUserBrief,
)
from app.modules.tasks.types import (
    ACTIVE_TASK_STATUSES,
    TASK_TYPE_LABELS,
    TASK_TYPE_SORT_ORDER,
    TaskStatus,
    TaskType,
)
from app.realtime.events import publish
from app.realtime.topics import (
    TASK_CONFIRMED,
    TASK_CREATED,
    TASK_DONE_PENDING,
    TASK_DUE_SOON,
    TASK_UPDATED,
)
from app.shared.exceptions import NotFound, PermissionDenied, ValidationError

DUE_SOON_WINDOW = timedelta(hours=24)


class TaskService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = TaskRepository(session)
        self._scope_loader = ScopeLoader(session)

    async def _ctx(self, actor: User) -> ScopeContext:
        return await self._scope_loader.load(actor)

    def _role(self, actor: User) -> UserRole:
        return actor.role if isinstance(actor.role, UserRole) else UserRole(str(actor.role))

    def _is_senior_or_admin(self, actor: User) -> bool:
        role = self._role(actor)
        return role in (UserRole.SENIOR, UserRole.GROUP_SENIOR, UserRole.ADMIN)

    async def _load_user(self, user_id: int) -> User:
        user = await self._session.get(User, user_id)
        if user is None:
            raise ValidationError(message="Пользователь не найден")
        return user

    async def _ensure_department_access(self, ctx: ScopeContext, department_id: int) -> None:
        visible = visible_department_ids(ctx)
        if visible != SCOPE_ALL and department_id not in visible:
            raise NotFound(message="Задача не найдена")

    async def _ensure_task_visible(self, actor: User, task: DepartmentTask) -> None:
        ctx = await self._ctx(actor)
        role = self._role(actor)
        if role == UserRole.ADMIN:
            return
        if role in (UserRole.SENIOR, UserRole.GROUP_SENIOR):
            await self._ensure_department_access(ctx, task.department_id)
            return
        if task.assignee_id != actor.id:
            raise NotFound(message="Задача не найдена")

    def _task_flags(self, task: DepartmentTask, now: datetime) -> tuple[bool, bool]:
        is_overdue = (
            task.status == TaskStatus.OPEN.value
            and task.due_at is not None
            and task.due_at < now
        )
        due_soon = (
            task.status == TaskStatus.OPEN.value
            and task.due_at is not None
            and now <= task.due_at <= now + DUE_SOON_WINDOW
        )
        return is_overdue, due_soon

    async def _users_map(self, user_ids: set[int]) -> dict[int, User]:
        if not user_ids:
            return {}
        result = await self._session.execute(select(User).where(User.id.in_(user_ids)))
        return {u.id: u for u in result.scalars().all()}

    def _to_response(
        self,
        task: DepartmentTask,
        *,
        users: dict[int, User],
        now: datetime,
    ) -> TaskResponse:
        task_type = TaskType(task.task_type)
        is_overdue, due_soon = self._task_flags(task, now)
        creator = users.get(task.created_by)
        assignee = users.get(task.assignee_id)
        return TaskResponse(
            id=task.id,
            department_id=task.department_id,
            title=task.title,
            description=task.description,
            task_type=task.task_type,
            task_type_label=TASK_TYPE_LABELS.get(task_type, task.task_type),
            status=task.status,
            created_by=task.created_by,
            assignee_id=task.assignee_id,
            due_at=task.due_at,
            completed_at=task.completed_at,
            completed_by=task.completed_by,
            confirmed_at=task.confirmed_at,
            confirmed_by=task.confirmed_by,
            created_at=task.created_at,
            updated_at=task.updated_at,
            is_overdue=is_overdue,
            due_soon=due_soon,
            creator=TaskUserBrief(id=creator.id, full_name=creator.full_name) if creator else None,
            assignee=TaskUserBrief(id=assignee.id, full_name=assignee.full_name) if assignee else None,
        )

    async def _build_responses(self, tasks: list[DepartmentTask]) -> list[TaskResponse]:
        now = datetime.now(UTC)
        user_ids: set[int] = set()
        for task in tasks:
            user_ids.add(task.created_by)
            user_ids.add(task.assignee_id)
        users = await self._users_map(user_ids)
        return [self._to_response(t, users=users, now=now) for t in tasks]

    async def list_my_tasks(self, actor: User) -> TaskListResponse:
        rows = self._repo.sort_tasks_for_assignee(await self._repo.list_for_assignee(actor.id))
        items = await self._build_responses(rows)
        return TaskListResponse(items=items, total=len(items))

    async def board(
        self,
        actor: User,
        *,
        department_id: int | None = None,
    ) -> TaskBoardResponse:
        if not self._is_senior_or_admin(actor):
            raise PermissionDenied(message="Доска задач доступна старшему оператору")
        ctx = await self._ctx(actor)
        role = self._role(actor)
        visible = visible_department_ids(ctx)

        if role == UserRole.ADMIN:
            if department_id is not None:
                await self._ensure_department_access(ctx, department_id)
                dept_ids: list[int] | None = [department_id]
            elif visible == SCOPE_ALL:
                dept_ids = None
            else:
                dept_ids = list(visible)
        else:
            dept_id = actor.department_id
            if dept_id is None:
                raise ValidationError(message="Отдел не назначен")
            if department_id is not None and department_id != dept_id:
                raise PermissionDenied(message="Нет доступа к доске этого отдела")
            await self._ensure_department_access(ctx, dept_id)
            dept_ids = [dept_id]

        active_rows = await self._repo.list_for_departments(dept_ids)
        closed_rows = await self._repo.list_closed_for_departments(dept_ids, limit=50)
        responses = await self._build_responses([*active_rows, *closed_rows])
        by_status: dict[str, list[TaskResponse]] = {
            TaskStatus.OPEN.value: [],
            TaskStatus.DONE_PENDING.value: [],
            TaskStatus.CLOSED.value: [],
        }
        for item in responses:
            if item.status in by_status:
                by_status[item.status].append(item)

        columns = [
            TaskBoardColumn(
                status=TaskStatus.OPEN.value,
                label="В работе",
                items=by_status[TaskStatus.OPEN.value],
            ),
            TaskBoardColumn(
                status=TaskStatus.DONE_PENDING.value,
                label="На проверке",
                items=by_status[TaskStatus.DONE_PENDING.value],
            ),
            TaskBoardColumn(
                status=TaskStatus.CLOSED.value,
                label="Готово",
                items=by_status[TaskStatus.CLOSED.value],
            ),
        ]
        task_types = [
            {"value": t.value, "label": TASK_TYPE_LABELS[t], "sort_order": TASK_TYPE_SORT_ORDER[t]}
            for t in TaskType
        ]
        return TaskBoardResponse(columns=columns, task_types=task_types)

    async def create(self, actor: User, body: TaskCreateRequest) -> TaskResponse:
        if not self._is_senior_or_admin(actor):
            raise PermissionDenied(message="Создавать задачи может только старший оператор")
        ctx = await self._ctx(actor)
        role = self._role(actor)
        assignee = await self._load_user(body.assignee_id)

        dept_id = actor.department_id
        if role == UserRole.ADMIN:
            if body.department_id is not None:
                dept_id = body.department_id
                await self._ensure_department_access(ctx, dept_id)
            elif dept_id is None:
                dept_id = assignee.department_id
                if dept_id is None:
                    raise ValidationError(message="Укажите отдел или выберите исполнителя с отделом")
        elif dept_id is None:
            raise ValidationError(message="Отдел не назначен")

        if assignee.department_id != dept_id and role != UserRole.ADMIN:
            raise ValidationError(message="Исполнитель должен быть из вашего отдела")
        if role == UserRole.ADMIN and assignee.department_id is not None and assignee.department_id != dept_id:
            raise ValidationError(message="Исполнитель должен быть из выбранного отдела")
        if not can_act_on_user(ctx, assignee.id):
            raise ValidationError(message="Нельзя назначить этого исполнителя")
        if body.task_type not in TaskType:
            raise ValidationError(message="Неверный тип задачи")

        row = DepartmentTask(
            department_id=dept_id,
            title=body.title.strip(),
            description=body.description.strip() if body.description else None,
            task_type=body.task_type.value,
            status=TaskStatus.OPEN.value,
            created_by=actor.id,
            assignee_id=assignee.id,
            due_at=body.due_at,
        )
        row = await self._repo.create(row)
        response = (await self._build_responses([row]))[0]
        payload = self._event_payload(row)
        await publish(TASK_CREATED, payload, scope={"user_id": row.assignee_id})
        await publish(TASK_CREATED, payload, scope={"department_id": row.department_id})
        return response

    async def update(self, actor: User, task_id: int, body: TaskUpdateRequest) -> TaskResponse:
        if not self._is_senior_or_admin(actor):
            raise PermissionDenied(message="Редактировать задачи может только старший оператор")
        task = await self._repo.get_by_id(task_id)
        if task is None or task.status not in {s.value for s in ACTIVE_TASK_STATUSES}:
            raise NotFound(message="Задача не найдена")
        await self._ensure_task_visible(actor, task)
        ctx = await self._ctx(actor)

        if body.title is not None:
            task.title = body.title.strip()
        if body.description is not None:
            task.description = body.description.strip() or None
        if body.task_type is not None:
            task.task_type = body.task_type.value
        if "due_at" in body.model_fields_set:
            task.due_at = body.due_at
            task.due_reminder_sent_at = None
        if body.assignee_id is not None:
            assignee = await self._load_user(body.assignee_id)
            if assignee.department_id != task.department_id:
                raise ValidationError(message="Исполнитель должен быть из отдела задачи")
            if not can_act_on_user(ctx, assignee.id):
                raise ValidationError(message="Нельзя назначить этого исполнителя")
            task.assignee_id = assignee.id

        task = await self._repo.save(task)
        response = (await self._build_responses([task]))[0]
        await publish(TASK_UPDATED, self._event_payload(task), scope={"user_id": task.assignee_id})
        await publish(
            TASK_UPDATED,
            self._event_payload(task),
            scope={"department_id": task.department_id},
        )
        return response

    async def move(self, actor: User, task_id: int, body: TaskMoveRequest) -> TaskResponse:
        if not self._is_senior_or_admin(actor):
            raise PermissionDenied(message="Управлять доской может только старший оператор")
        target = body.status
        task = await self._repo.get_by_id(task_id)
        if task is None:
            raise NotFound(message="Задача не найдена")
        await self._ensure_task_visible(actor, task)
        now = datetime.now(UTC)

        if target == TaskStatus.OPEN:
            task.status = TaskStatus.OPEN.value
            task.completed_at = None
            task.completed_by = None
            task.confirmed_at = None
            task.confirmed_by = None
        elif target == TaskStatus.DONE_PENDING:
            task.status = TaskStatus.DONE_PENDING.value
            if task.completed_at is None:
                task.completed_at = now
                task.completed_by = actor.id
            task.confirmed_at = None
            task.confirmed_by = None
        else:
            task.status = TaskStatus.CLOSED.value
            if task.completed_at is None:
                task.completed_at = now
                task.completed_by = actor.id
            task.confirmed_at = now
            task.confirmed_by = actor.id

        # Ручной порядок нужен только для активных колонок; закрытые сортируются по дате.
        if target != TaskStatus.CLOSED:
            await self._repo.reorder_column(task, status=task.status, position=body.position)
        task = await self._repo.save(task)
        response = (await self._build_responses([task]))[0]
        payload = self._event_payload(task)
        await publish(TASK_UPDATED, payload, scope={"user_id": task.assignee_id})
        await publish(TASK_UPDATED, payload, scope={"department_id": task.department_id})
        return response

    async def complete(self, actor: User, task_id: int) -> TaskResponse:
        task = await self._repo.get_by_id(task_id)
        if task is None or task.status != TaskStatus.OPEN.value:
            raise NotFound(message="Задача не найдена")
        if task.assignee_id != actor.id:
            raise PermissionDenied(message="Отметить выполнение может только исполнитель")
        now = datetime.now(UTC)
        task.status = TaskStatus.DONE_PENDING.value
        task.completed_at = now
        task.completed_by = actor.id
        task = await self._repo.save(task)
        response = (await self._build_responses([task]))[0]
        await publish(
            TASK_DONE_PENDING,
            self._event_payload(task),
            scope={"department_id": task.department_id},
        )
        return response

    async def confirm(self, actor: User, task_id: int) -> TaskResponse:
        if not self._is_senior_or_admin(actor):
            raise PermissionDenied(message="Подтверждать задачи может только старший оператор")
        task = await self._repo.get_by_id(task_id)
        if task is None or task.status != TaskStatus.DONE_PENDING.value:
            raise NotFound(message="Задача не найдена")
        await self._ensure_task_visible(actor, task)
        now = datetime.now(UTC)
        task.status = TaskStatus.CLOSED.value
        task.confirmed_at = now
        task.confirmed_by = actor.id
        task = await self._repo.save(task)
        response = (await self._build_responses([task]))[0]
        await publish(
            TASK_CONFIRMED,
            self._event_payload(task),
            scope={"user_id": task.assignee_id},
        )
        await publish(
            TASK_CONFIRMED,
            self._event_payload(task),
            scope={"department_id": task.department_id},
        )
        return response

    async def reopen(self, actor: User, task_id: int) -> TaskResponse:
        if not self._is_senior_or_admin(actor):
            raise PermissionDenied(message="Вернуть задачу может только старший оператор")
        task = await self._repo.get_by_id(task_id)
        if task is None or task.status != TaskStatus.DONE_PENDING.value:
            raise NotFound(message="Задача не найдена")
        await self._ensure_task_visible(actor, task)
        task.status = TaskStatus.OPEN.value
        task.completed_at = None
        task.completed_by = None
        task = await self._repo.save(task)
        response = (await self._build_responses([task]))[0]
        await publish(TASK_UPDATED, self._event_payload(task), scope={"user_id": task.assignee_id})
        await publish(
            TASK_UPDATED,
            self._event_payload(task),
            scope={"department_id": task.department_id},
        )
        return response

    async def delete(self, actor: User, task_id: int) -> None:
        if not self._is_senior_or_admin(actor):
            raise PermissionDenied(message="Удалять задачи может только старший оператор")
        task = await self._repo.get_by_id(task_id)
        if task is None or task.status not in {s.value for s in ACTIVE_TASK_STATUSES}:
            raise NotFound(message="Задача не найдена")
        await self._ensure_task_visible(actor, task)
        task.status = TaskStatus.CLOSED.value
        task.confirmed_at = datetime.now(UTC)
        task.confirmed_by = actor.id
        await self._repo.save(task)
        await publish(TASK_CONFIRMED, self._event_payload(task), scope={"user_id": task.assignee_id})
        await publish(
            TASK_CONFIRMED,
            self._event_payload(task),
            scope={"department_id": task.department_id},
        )

    @staticmethod
    def _event_payload(task: DepartmentTask) -> dict[str, object]:
        return {
            "task_id": task.id,
            "department_id": task.department_id,
            "assignee_id": task.assignee_id,
            "status": task.status,
            "task_type": task.task_type,
            "title": task.title,
            "due_at": task.due_at.isoformat() if task.due_at else None,
        }

    async def send_due_reminders(self) -> int:
        now = datetime.now(UTC)
        tasks = await self._repo.list_due_for_reminder(now=now, within=DUE_SOON_WINDOW)
        count = 0
        for task in tasks:
            await publish(
                TASK_DUE_SOON,
                {
                    **self._event_payload(task),
                    "message": "Срок выполнения задачи подходит к концу",
                },
                scope={"user_id": task.assignee_id},
            )
            await self._repo.mark_reminder_sent(task.id, now)
            count += 1
        return count
