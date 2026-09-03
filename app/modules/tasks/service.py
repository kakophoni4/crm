from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.contacts.scope_loader import ScopeLoader
from app.modules.db.models.department_task import DepartmentTask
from app.modules.db.models.enums import AuditAction, UserRole, UserStatus
from app.modules.db.models.user import User
from app.modules.rbac.scope import SCOPE_ALL, ScopeContext, visible_department_ids, visible_user_ids
from app.modules.tasks.history import format_task_history_summary
from app.modules.tasks.repository import TaskRepository
from app.modules.tasks.schemas import (
    ClientRequirementAccountantOption,
    TaskAssigneeListResponse,
    TaskAssigneeOption,
    TaskBoardColumn,
    TaskBoardResponse,
    TaskChildBrief,
    TaskCommentListResponse,
    TaskCommentResponse,
    TaskCreateRequest,
    TaskDetailResponse,
    TaskFileBrief,
    TaskHistoryItem,
    TaskHistoryResponse,
    TaskListResponse,
    TaskMoveRequest,
    TaskResponse,
    TaskUpdateRequest,
    TaskUserBrief,
    TaskWorkloadSummary,
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
    TASK_NOTIFY,
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

    def _is_admin(self, actor: User) -> bool:
        return self._role(actor) == UserRole.ADMIN

    def _is_senior_or_admin(self, actor: User) -> bool:
        role = self._role(actor)
        return role in (
            UserRole.SENIOR,
            UserRole.GROUP_SENIOR,
            UserRole.ADMIN,
            UserRole.CHIEF_ACCOUNTANT,
        )

    def _can_review_completion(self, actor: User, task: DepartmentTask) -> bool:
        if self._is_senior_or_admin(actor):
            return True
        return task.created_by == actor.id

    def _can_create_task(self, actor: User) -> bool:
        if self._is_senior_or_admin(actor):
            return True
        return self._role(actor) in {UserRole.USER, UserRole.LAWYER}

    async def _load_user(self, user_id: int) -> User:
        user = await self._session.get(User, user_id)
        if user is None:
            raise ValidationError(message="Пользователь не найден")
        return user

    async def _ensure_active_assignee(self, user_id: int) -> User:
        user = await self._load_user(user_id)
        status = user.status if isinstance(user.status, UserStatus) else UserStatus(str(user.status))
        if status != UserStatus.ACTIVE:
            raise ValidationError(message="Исполнитель неактивен")
        return user

    async def _resolve_department_for_task(
        self,
        actor: User,
        assignee: User,
        preferred_department_id: int | None = None,
    ) -> int:
        from app.modules.db.models.department import Department

        for candidate in (preferred_department_id, actor.department_id, assignee.department_id):
            if candidate is not None:
                return int(candidate)
        user_dept = (
            await self._session.execute(
                select(User.department_id)
                .where(User.department_id.is_not(None))
                .order_by(User.id.asc())
                .limit(1),
            )
        ).scalar_one_or_none()
        if user_dept is not None:
            return int(user_dept)
        dept_row = (
            await self._session.execute(
                select(Department.id).order_by(Department.id.asc()).limit(1),
            )
        ).scalar_one_or_none()
        if dept_row is not None:
            return int(dept_row)
        dept = Department(name="Общий")
        self._session.add(dept)
        await self._session.flush()
        return int(dept.id)

    def _assignee_option(self, user: User) -> TaskAssigneeOption:
        role = user.role.value if hasattr(user.role, "value") else str(user.role)
        return TaskAssigneeOption(
            id=user.id,
            full_name=user.full_name or f"user #{user.id}",
            role=role,
            department_id=user.department_id,
        )

    async def list_assignees(self, actor: User) -> TaskAssigneeListResponse:
        result = await self._session.execute(
            select(User)
            .where(User.status == UserStatus.ACTIVE)
            .order_by(User.full_name)
            .limit(500),
        )
        users = list(result.scalars().all())
        users.sort(
            key=lambda u: (0 if u.id == actor.id else 1, (u.full_name or "").casefold()),
        )
        return TaskAssigneeListResponse(items=[self._assignee_option(u) for u in users])

    async def _ensure_department_access(self, ctx: ScopeContext, department_id: int) -> None:
        visible = visible_department_ids(ctx)
        if visible != SCOPE_ALL and department_id not in visible:
            raise NotFound(message="Задача не найдена")

    async def _ensure_task_visible(self, actor: User, task: DepartmentTask) -> None:
        if task.status == TaskStatus.DELETED.value and not self._is_admin(actor):
            raise NotFound(message="Задача не найдена")
        ctx = await self._ctx(actor)
        role = self._role(actor)
        if role in (UserRole.ADMIN, UserRole.CHIEF_ACCOUNTANT):
            return
        if role in (UserRole.SENIOR, UserRole.GROUP_SENIOR):
            await self._ensure_department_access(ctx, task.department_id)
            return
        if task.assignee_id == actor.id or task.created_by == actor.id:
            return
        if actor.id in await self._collaborator_ids(task.id):
            return
        raise NotFound(message="Задача не найдена")

    async def actor_can_access_file(self, actor: User, file_id: int) -> bool:
        from app.modules.db.models.department_task_file import DepartmentTaskFile

        result = await self._session.execute(
            select(DepartmentTaskFile.task_id).where(DepartmentTaskFile.file_id == file_id),
        )
        task_ids = {int(tid) for tid in result.scalars().all()}
        for task_id in task_ids:
            task = await self._repo.get_by_id(task_id)
            if task is None:
                continue
            try:
                await self._ensure_task_visible(actor, task)
            except NotFound:
                continue
            return True
        return False

    async def _collaborator_ids(self, task_id: int) -> set[int]:
        from app.modules.db.models.department_task_collaborator import (
            DepartmentTaskCollaborator,
        )

        result = await self._session.execute(
            select(DepartmentTaskCollaborator.user_id).where(
                DepartmentTaskCollaborator.task_id == task_id,
            ),
        )
        return {int(uid) for uid in result.scalars().all()}

    async def _is_working_on(self, actor: User, task: DepartmentTask) -> bool:
        if task.assignee_id == actor.id:
            return True
        return actor.id in await self._collaborator_ids(task.id)

    async def _can_change_assignee(self, actor: User, task: DepartmentTask) -> bool:
        if actor.id in {task.created_by, task.assignee_id}:
            return True
        role = self._role(actor)
        if role in {UserRole.ADMIN, UserRole.CHIEF_ACCOUNTANT}:
            return True
        if role == UserRole.SENIOR:
            ctx = await self._ctx(actor)
            visible = visible_department_ids(ctx)
            return visible == SCOPE_ALL or task.department_id in visible
        if role == UserRole.GROUP_SENIOR:
            ctx = await self._ctx(actor)
            users = visible_user_ids(ctx)
            return users == SCOPE_ALL or task.assignee_id in users
        return False

    async def _can_handoff(self, actor: User, task: DepartmentTask) -> bool:
        if await self._can_change_assignee(actor, task):
            return True
        return await self._is_working_on(actor, task)

    async def _ensure_assignee_target_allowed(self, actor: User, task: DepartmentTask, next_user: User) -> None:
        if actor.id in {task.created_by, task.assignee_id}:
            return
        role = self._role(actor)
        if role in {UserRole.ADMIN, UserRole.CHIEF_ACCOUNTANT}:
            return
        if role == UserRole.SENIOR:
            if (
                actor.department_id is not None
                and next_user.department_id is not None
                and next_user.department_id != actor.department_id
            ):
                raise PermissionDenied(message="Можно назначить только сотрудника своего отдела")
            return
        if role == UserRole.GROUP_SENIOR:
            ctx = await self._ctx(actor)
            users = visible_user_ids(ctx)
            if users != SCOPE_ALL and next_user.id not in users:
                raise PermissionDenied(message="Можно назначить только сотрудника своей группы")
            return

    async def _attach_files(self, task_id: int, file_ids: list[int] | None) -> None:
        from app.modules.db.models.department_task_file import DepartmentTaskFile
        from app.modules.db.models.uploaded_file import UploadedFile

        ids = [int(fid) for fid in (file_ids or []) if int(fid) > 0]
        if not ids:
            return
        existing = await self._session.execute(
            select(DepartmentTaskFile.file_id).where(
                DepartmentTaskFile.task_id == task_id,
                DepartmentTaskFile.file_id.in_(ids),
            ),
        )
        already = {int(x) for x in existing.scalars().all()}
        valid = await self._session.execute(
            select(UploadedFile.id).where(UploadedFile.id.in_(ids)),
        )
        valid_ids = {int(x) for x in valid.scalars().all()}
        for fid in ids:
            if fid in already or fid not in valid_ids:
                continue
            self._session.add(DepartmentTaskFile(task_id=task_id, file_id=fid))
        await self._session.flush()

    async def _add_comment_row(
        self,
        task: DepartmentTask,
        actor: User,
        body: str,
        *,
        file_ids: list[int] | None = None,
    ):
        from app.modules.db.models.department_task_comment import DepartmentTaskComment

        text = (body or "").strip()
        files = [int(fid) for fid in (file_ids or []) if int(fid) > 0]
        if not text and not files:
            return None
        if not text:
            text = "Прикреплены файлы"
        await self._attach_files(task.id, files)
        row = DepartmentTaskComment(task_id=task.id, author_id=actor.id, body=text)
        self._session.add(row)
        await self._session.flush()
        return row

    async def _add_collaborator(
        self,
        task: DepartmentTask,
        user_id: int,
        *,
        added_by: int,
    ) -> None:
        from app.modules.db.models.department_task_collaborator import (
            DepartmentTaskCollaborator,
        )

        if user_id == task.assignee_id:
            return
        existing = await self._session.get(
            DepartmentTaskCollaborator,
            (task.id, user_id),
        )
        if existing is not None:
            return
        self._session.add(
            DepartmentTaskCollaborator(
                task_id=task.id,
                user_id=user_id,
                added_by=added_by,
            ),
        )
        await self._session.flush()

    def _task_flags(self, task: DepartmentTask, now: datetime) -> tuple[bool, bool]:
        active = task.status in {TaskStatus.NEW.value, TaskStatus.OPEN.value}
        due = task.due_at
        if due is not None and due.tzinfo is None:
            due = due.replace(tzinfo=UTC)
        now_utc = now if now.tzinfo is not None else now.replace(tzinfo=UTC)
        is_overdue = active and due is not None and due < now_utc
        due_soon = (
            active
            and due is not None
            and now_utc <= due <= now_utc + DUE_SOON_WINDOW
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
        file_ids: list[int] | None = None,
        files: list[TaskFileBrief] | None = None,
        collaborators: list[TaskUserBrief] | None = None,
    ) -> TaskResponse:
        task_type: TaskType
        try:
            task_type = TaskType(task.task_type)
        except ValueError:
            task_type = TaskType.NORMAL
        is_overdue, due_soon = self._task_flags(task, now)
        creator = users.get(task.created_by)
        assignee = users.get(task.assignee_id)
        needs_ack = (
            task.status == TaskStatus.NEW.value
            and (getattr(task, "source", None) or "manual") == "fns_requirement"
        )
        return TaskResponse(
            id=task.id,
            department_id=task.department_id,
            title=task.title,
            description=task.description,
            task_type=task.task_type,
            task_type_label=TASK_TYPE_LABELS.get(task_type, task.task_type),
            status=task.status,
            source=getattr(task, "source", None) or "manual",
            opt_unit_id=getattr(task, "opt_unit_id", None),
            opt_requirement_id=getattr(task, "opt_requirement_id", None),
            chat_id=getattr(task, "chat_id", None),
            lead_id=getattr(task, "lead_id", None),
            parent_task_id=getattr(task, "parent_task_id", None),
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
            needs_ack=needs_ack,
            creator=TaskUserBrief(id=creator.id, full_name=creator.full_name) if creator else None,
            assignee=TaskUserBrief(id=assignee.id, full_name=assignee.full_name) if assignee else None,
            collaborators=collaborators or [],
            file_ids=file_ids or [],
            files=files or [],
        )

    async def _files_by_task(
        self,
        task_ids: list[int],
    ) -> dict[int, list[TaskFileBrief]]:
        if not task_ids:
            return {}
        from app.modules.db.models.department_task_file import DepartmentTaskFile
        from app.modules.db.models.uploaded_file import UploadedFile

        result = await self._session.execute(
            select(DepartmentTaskFile, UploadedFile)
            .join(UploadedFile, UploadedFile.id == DepartmentTaskFile.file_id)
            .where(DepartmentTaskFile.task_id.in_(task_ids))
            .order_by(DepartmentTaskFile.id),
        )
        out: dict[int, list[TaskFileBrief]] = {}
        for link, uploaded in result.all():
            out.setdefault(int(link.task_id), []).append(
                TaskFileBrief(
                    id=uploaded.id,
                    original_name=uploaded.original_name,
                    mime_type=uploaded.mime_type,
                    size_bytes=int(uploaded.size_bytes),
                ),
            )
        return out

    async def _collaborators_by_task(
        self,
        task_ids: list[int],
    ) -> dict[int, list[int]]:
        if not task_ids:
            return {}
        from app.modules.db.models.department_task_collaborator import (
            DepartmentTaskCollaborator,
        )

        result = await self._session.execute(
            select(
                DepartmentTaskCollaborator.task_id,
                DepartmentTaskCollaborator.user_id,
            ).where(DepartmentTaskCollaborator.task_id.in_(task_ids)),
        )
        out: dict[int, list[int]] = {}
        for task_id, user_id in result.all():
            out.setdefault(int(task_id), []).append(int(user_id))
        return out

    async def _build_responses(self, tasks: list[DepartmentTask]) -> list[TaskResponse]:
        now = datetime.now(UTC)
        user_ids: set[int] = set()
        for task in tasks:
            user_ids.add(task.created_by)
            user_ids.add(task.assignee_id)
        collab_map = await self._collaborators_by_task([t.id for t in tasks])
        for uids in collab_map.values():
            user_ids.update(uids)
        users = await self._users_map(user_ids)
        files_map = await self._files_by_task([t.id for t in tasks])
        return [
            self._to_response(
                t,
                users=users,
                now=now,
                file_ids=[f.id for f in files_map.get(t.id, [])],
                files=files_map.get(t.id, []),
                collaborators=[
                    TaskUserBrief(id=users[uid].id, full_name=users[uid].full_name)
                    for uid in collab_map.get(t.id, [])
                    if uid in users
                ],
            )
            for t in tasks
        ]

    async def _write_history(
        self,
        actor: User,
        task: DepartmentTask,
        action: AuditAction,
        payload: dict | None = None,
    ) -> None:
        from app.modules.audit.service import AuditService

        await AuditService(self._session).write(
            actor_id=actor.id,
            action=action,
            entity_type="task",
            entity_id=task.id,
            payload=payload or {},
        )

    @staticmethod
    def _iso(value: datetime | None) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC).isoformat()
        return value.isoformat()

    def _workload_summary(self, items: list[TaskResponse]) -> TaskWorkloadSummary:
        return TaskWorkloadSummary(
            total=len(items),
            new=sum(1 for item in items if item.status == TaskStatus.NEW.value),
            open=sum(1 for item in items if item.status == TaskStatus.OPEN.value),
            overdue=sum(1 for item in items if item.is_overdue),
            pending_review=sum(1 for item in items if item.status == TaskStatus.DONE_PENDING.value),
            done=sum(1 for item in items if item.status == TaskStatus.CLOSED.value),
            deleted=sum(1 for item in items if item.status == TaskStatus.DELETED.value),
        )

    def _filter_statuses(
        self,
        actor: User,
        *,
        status: TaskStatus | None,
        include_closed: bool,
        include_deleted: bool = False,
    ) -> list[str] | None:
        is_admin = self._is_admin(actor)
        if status is not None:
            if status == TaskStatus.DELETED and not is_admin:
                return []
            return [status.value]
        statuses = [item.value for item in ACTIVE_TASK_STATUSES]
        if include_closed:
            statuses.append(TaskStatus.CLOSED.value)
        if include_deleted and is_admin:
            statuses.append(TaskStatus.DELETED.value)
        return statuses

    async def list_my_tasks(
        self,
        actor: User,
        *,
        assignee_id: int | None = None,
        created_by: int | None = None,
        q: str | None = None,
        status: TaskStatus | None = None,
        include_closed: bool = False,
    ) -> TaskListResponse:
        needle = (q or "").strip() or None
        has_filters = any([assignee_id, created_by, needle, status])
        if not has_filters:
            rows = self._repo.sort_tasks_for_assignee(
                await self._repo.list_for_assignee(actor.id, include_closed=include_closed),
            )
        else:
            rows = self._repo.sort_tasks_for_assignee(
                await self._repo.list_filtered(
                    related_user_id=actor.id,
                    assignee_id=assignee_id,
                    created_by=created_by,
                    statuses=self._filter_statuses(
                        actor,
                        status=status,
                        include_closed=include_closed,
                    ),
                    q=needle,
                ),
            )
        items = await self._build_responses(rows)
        return TaskListResponse(items=items, total=len(items), summary=self._workload_summary(items))

    async def board(
        self,
        actor: User,
        *,
        department_id: int | None = None,
        assignee_id: int | None = None,
        created_by: int | None = None,
        q: str | None = None,
        status: TaskStatus | None = None,
        include_closed: bool = False,
    ) -> TaskBoardResponse:
        if not self._is_senior_or_admin(actor):
            raise PermissionDenied(message="Доска задач доступна старшему оператору")
        ctx = await self._ctx(actor)
        role = self._role(actor)
        visible = visible_department_ids(ctx)

        if role in (UserRole.ADMIN, UserRole.CHIEF_ACCOUNTANT):
            if department_id is not None:
                await self._ensure_department_access(ctx, department_id)
                dept_ids: list[int] | None = [department_id]
            elif visible == SCOPE_ALL or role == UserRole.CHIEF_ACCOUNTANT:
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

        needle = (q or "").strip() or None
        filtered = any([assignee_id, created_by, needle, status])
        is_admin = self._is_admin(actor)
        show_closed = bool(include_closed)
        if filtered:
            rows = await self._repo.list_filtered(
                department_ids=dept_ids,
                assignee_id=assignee_id,
                created_by=created_by,
                statuses=self._filter_statuses(
                    actor,
                    status=status,
                    include_closed=show_closed,
                    include_deleted=is_admin,
                ),
                q=needle,
            )
        else:
            active_rows = await self._repo.list_for_departments(dept_ids)
            closed_rows = (
                await self._repo.list_status_for_departments(
                    dept_ids,
                    status=TaskStatus.CLOSED.value,
                    limit=80,
                )
                if show_closed
                else []
            )
            deleted_rows = (
                await self._repo.list_status_for_departments(
                    dept_ids,
                    status=TaskStatus.DELETED.value,
                    limit=80,
                )
                if is_admin
                else []
            )
            rows = [*active_rows, *closed_rows, *deleted_rows]
        responses = await self._build_responses(rows)
        by_status: dict[str, list[TaskResponse]] = {
            TaskStatus.NEW.value: [],
            TaskStatus.OPEN.value: [],
            TaskStatus.DONE_PENDING.value: [],
            TaskStatus.CLOSED.value: [],
            TaskStatus.DELETED.value: [],
        }
        for item in responses:
            if item.status in by_status:
                by_status[item.status].append(item)

        now = datetime.now(UTC)
        for status, items in by_status.items():
            by_status[status] = self._repo.sort_task_items(items, now=now, mode="due")

        columns = [
            TaskBoardColumn(
                status=TaskStatus.NEW.value,
                label="Новые",
                items=by_status[TaskStatus.NEW.value],
            ),
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
        ]
        if show_closed:
            columns.append(
                TaskBoardColumn(
                    status=TaskStatus.CLOSED.value,
                    label="Готово",
                    items=by_status[TaskStatus.CLOSED.value],
                ),
            )
        if is_admin:
            columns.append(
                TaskBoardColumn(
                    status=TaskStatus.DELETED.value,
                    label="Удалённые",
                    items=by_status[TaskStatus.DELETED.value],
                ),
            )
        task_types = [
            {"value": t.value, "label": TASK_TYPE_LABELS[t], "sort_order": TASK_TYPE_SORT_ORDER[t]}
            for t in TaskType
        ]
        return TaskBoardResponse(
            columns=columns,
            task_types=task_types,
            summary=self._workload_summary(responses),
        )

    async def create(self, actor: User, body: TaskCreateRequest) -> TaskResponse:
        if not self._can_create_task(actor):
            raise PermissionDenied(message="Недостаточно прав, чтобы поставить задачу")
        ctx = await self._ctx(actor)
        role = self._role(actor)
        assignee = await self._ensure_active_assignee(body.assignee_id)

        preferred_dept = body.department_id if role == UserRole.ADMIN else actor.department_id
        if role == UserRole.ADMIN and body.department_id is not None:
            await self._ensure_department_access(ctx, body.department_id)
        dept_id = await self._resolve_department_for_task(actor, assignee, preferred_dept)

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
        await self._attach_files(row.id, body.file_ids)
        await self._write_history(
            actor,
            row,
            AuditAction.TASK_CREATE,
            {
                "kind": "create",
                "title": row.title,
                "assignee_id": assignee.id,
                "assignee_name": assignee.full_name,
            },
        )
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

        changes: dict[str, dict[str, object | None]] = {}

        if body.title is not None:
            title = body.title.strip()
            if title != task.title:
                changes["title"] = {"from": task.title, "to": title}
            task.title = title
        if body.description is not None:
            description = body.description.strip() or None
            if description != task.description:
                changes["description"] = {"from": task.description, "to": description}
            task.description = description
        if body.task_type is not None:
            next_type = body.task_type.value
            if next_type != task.task_type:
                changes["task_type"] = {"from": task.task_type, "to": next_type}
            task.task_type = next_type
        if "due_at" in body.model_fields_set:
            if self._iso(body.due_at) != self._iso(task.due_at):
                changes["due_at"] = {"from": self._iso(task.due_at), "to": self._iso(body.due_at)}
            task.due_at = body.due_at
            task.due_reminder_sent_at = None
        assignee_payload: dict[str, object] | None = None
        if body.assignee_id is not None:
            if not await self._can_change_assignee(actor, task):
                raise PermissionDenied(message="Нельзя сменить исполнителя этой задачи")
            assignee = await self._ensure_active_assignee(body.assignee_id)
            await self._ensure_assignee_target_allowed(actor, task, assignee)
            if assignee.id != task.assignee_id:
                previous = await self._load_user(task.assignee_id)
                assignee_payload = {
                    "kind": "assignee",
                    "from": previous.id,
                    "from_name": previous.full_name,
                    "to": assignee.id,
                    "to_name": assignee.full_name,
                }
            task.assignee_id = assignee.id

        task = await self._repo.save(task)
        if assignee_payload is not None:
            await self._write_history(actor, task, AuditAction.TASK_UPDATE, assignee_payload)
        if changes:
            await self._write_history(
                actor,
                task,
                AuditAction.TASK_UPDATE,
                {"kind": "fields", "changes": changes},
            )
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
        if target == TaskStatus.DELETED:
            await self._soft_delete(actor, task)
            return (await self._build_responses([task]))[0]
        if task.status == TaskStatus.DELETED.value and not self._is_admin(actor):
            raise NotFound(message="Задача не найдена")
        now = datetime.now(UTC)
        previous_status = task.status

        if target == TaskStatus.NEW:
            task.status = TaskStatus.NEW.value
            task.completed_at = None
            task.completed_by = None
            task.confirmed_at = None
            task.confirmed_by = None
        elif target == TaskStatus.OPEN:
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

        # Ручной порядок нужен только для активных колонок; архив сортируется по дате.
        if target not in {TaskStatus.CLOSED, TaskStatus.DELETED}:
            await self._repo.reorder_column(task, status=task.status, position=body.position)
        task = await self._repo.save(task)
        if previous_status != task.status:
            await self._write_history(
                actor,
                task,
                AuditAction.TASK_STATUS_UPDATE,
                {"kind": "move", "from": previous_status, "to": task.status},
            )
        response = (await self._build_responses([task]))[0]
        payload = self._event_payload(task)
        await publish(TASK_UPDATED, payload, scope={"user_id": task.assignee_id})
        await publish(TASK_UPDATED, payload, scope={"department_id": task.department_id})
        return response

    async def acknowledge(self, actor: User, task_id: int) -> TaskResponse:
        """Assignee moves new → open (stops manager blink for FNS tasks)."""
        task = await self._repo.get_by_id(task_id)
        if task is None or task.status != TaskStatus.NEW.value:
            raise NotFound(message="Задача не найдена")
        if task.assignee_id != actor.id and not self._is_senior_or_admin(actor):
            if not await self._is_working_on(actor, task):
                raise PermissionDenied(message="Принять задачу может только исполнитель")
        task.status = TaskStatus.OPEN.value
        task = await self._repo.save(task)
        await self._write_history(
            actor,
            task,
            AuditAction.TASK_STATUS_UPDATE,
            {"kind": "acknowledge", "from": TaskStatus.NEW.value, "to": task.status},
        )
        response = (await self._build_responses([task]))[0]
        await publish(TASK_UPDATED, self._event_payload(task), scope={"user_id": task.assignee_id})
        return response

    async def complete(
        self,
        actor: User,
        task_id: int,
        *,
        comment: str | None = None,
        file_ids: list[int] | None = None,
    ) -> TaskResponse:
        task = await self._repo.get_by_id(task_id)
        if task is None or task.status not in {TaskStatus.OPEN.value, TaskStatus.NEW.value}:
            raise NotFound(message="Задача не найдена")
        if not await self._is_working_on(actor, task) and not self._is_senior_or_admin(actor):
            raise PermissionDenied(message="Отметить выполнение может только исполнитель")
        previous = task.status
        await self._add_comment_row(task, actor, comment or "", file_ids=file_ids)
        now = datetime.now(UTC)
        task.status = TaskStatus.DONE_PENDING.value
        task.completed_at = now
        task.completed_by = actor.id
        task = await self._repo.save(task)
        await self._write_history(
            actor,
            task,
            AuditAction.TASK_STATUS_UPDATE,
            {"kind": "complete", "from": previous, "to": task.status},
        )
        response = (await self._build_responses([task]))[0]
        payload = self._event_payload(task)
        await publish(
            TASK_DONE_PENDING,
            payload,
            scope={"department_id": task.department_id},
        )
        if task.created_by and task.created_by != actor.id:
            await publish(TASK_DONE_PENDING, payload, scope={"user_id": task.created_by})
        return response

    async def confirm(self, actor: User, task_id: int) -> TaskResponse:
        task = await self._repo.get_by_id(task_id)
        if task is None or task.status != TaskStatus.DONE_PENDING.value:
            raise NotFound(message="Задача не найдена")
        await self._ensure_task_visible(actor, task)
        if not self._can_review_completion(actor, task):
            raise PermissionDenied(
                message="Подтвердить выполнение может постановщик или старший оператор",
            )
        now = datetime.now(UTC)
        task.status = TaskStatus.CLOSED.value
        task.confirmed_at = now
        task.confirmed_by = actor.id
        task = await self._repo.save(task)
        await self._write_history(
            actor,
            task,
            AuditAction.TASK_STATUS_UPDATE,
            {"kind": "confirm", "from": TaskStatus.DONE_PENDING.value, "to": task.status},
        )
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
        task = await self._repo.get_by_id(task_id)
        if task is None or task.status != TaskStatus.DONE_PENDING.value:
            raise NotFound(message="Задача не найдена")
        await self._ensure_task_visible(actor, task)
        if not self._can_review_completion(actor, task):
            raise PermissionDenied(
                message="Вернуть задачу в работу может постановщик или старший оператор",
            )
        task.status = TaskStatus.OPEN.value
        task.completed_at = None
        task.completed_by = None
        task = await self._repo.save(task)
        await self._write_history(
            actor,
            task,
            AuditAction.TASK_STATUS_UPDATE,
            {"kind": "reopen", "from": TaskStatus.DONE_PENDING.value, "to": task.status},
        )
        response = (await self._build_responses([task]))[0]
        await publish(TASK_UPDATED, self._event_payload(task), scope={"user_id": task.assignee_id})
        await publish(
            TASK_UPDATED,
            self._event_payload(task),
            scope={"department_id": task.department_id},
        )
        return response

    async def _soft_delete(self, actor: User, task: DepartmentTask) -> DepartmentTask:
        if task.status == TaskStatus.DELETED.value:
            return task
        allowed = {s.value for s in ACTIVE_TASK_STATUSES}
        if self._is_admin(actor):
            allowed.add(TaskStatus.CLOSED.value)
        if task.status not in allowed:
            raise NotFound(message="Задача не найдена")
        previous_status = task.status
        task.status = TaskStatus.DELETED.value
        task = await self._repo.save(task)
        await self._write_history(
            actor,
            task,
            AuditAction.TASK_DELETE,
            {"kind": "delete", "from": previous_status, "to": task.status},
        )
        await publish(TASK_UPDATED, self._event_payload(task), scope={"user_id": task.assignee_id})
        await publish(
            TASK_UPDATED,
            self._event_payload(task),
            scope={"department_id": task.department_id},
        )
        return task

    async def delete(self, actor: User, task_id: int, *, permanent: bool = False) -> None:
        task = await self._repo.get_by_id(task_id)
        if task is None:
            raise NotFound(message="Задача не найдена")
        if permanent:
            if not self._is_admin(actor):
                raise PermissionDenied(message="Безвозвратно удалить может только админ")
            if task.status != TaskStatus.DELETED.value:
                raise ValidationError(message="Сначала перенесите задачу в удалённые")
            await self._write_history(
                actor,
                task,
                AuditAction.TASK_DELETE,
                {"kind": "purge", "title": task.title},
            )
            payload = self._event_payload(task)
            await self._repo.hard_delete(task)
            await publish(TASK_UPDATED, payload, scope={"user_id": payload["assignee_id"]})
            await publish(TASK_UPDATED, payload, scope={"department_id": payload["department_id"]})
            return
        if not self._is_senior_or_admin(actor):
            raise PermissionDenied(message="Удалять задачи может только старший оператор")
        await self._ensure_task_visible(actor, task)
        await self._soft_delete(actor, task)

    async def get_task(self, actor: User, task_id: int) -> TaskDetailResponse:
        from app.modules.db.models.department_task_comment import DepartmentTaskComment

        task = await self._repo.get_by_id(task_id)
        if task is None:
            raise NotFound(message="Задача не найдена")
        await self._ensure_task_visible(actor, task)
        base = (await self._build_responses([task]))[0]
        comments_result = await self._session.execute(
            select(DepartmentTaskComment)
            .where(DepartmentTaskComment.task_id == task_id)
            .order_by(DepartmentTaskComment.created_at.asc())
            .limit(200),
        )
        comment_rows = list(comments_result.scalars().all())
        author_ids = {c.author_id for c in comment_rows}
        authors = await self._users_map(author_ids)
        comments = [
            TaskCommentResponse(
                id=c.id,
                task_id=c.task_id,
                author_id=c.author_id,
                body=c.body,
                created_at=c.created_at,
                author=(
                    TaskUserBrief(id=authors[c.author_id].id, full_name=authors[c.author_id].full_name)
                    if c.author_id in authors
                    else None
                ),
            )
            for c in comment_rows
        ]
        children_result = await self._session.execute(
            select(DepartmentTask)
            .where(DepartmentTask.parent_task_id == task_id)
            .order_by(DepartmentTask.id.desc())
            .limit(50),
        )
        child_rows = list(children_result.scalars().all())
        child_users = await self._users_map({c.assignee_id for c in child_rows})
        child_briefs = [
            TaskChildBrief(
                id=c.id,
                title=c.title,
                status=c.status,
                assignee=(
                    TaskUserBrief(
                        id=child_users[c.assignee_id].id,
                        full_name=child_users[c.assignee_id].full_name,
                    )
                    if c.assignee_id in child_users
                    else None
                ),
            )
            for c in child_rows
        ]
        return TaskDetailResponse(
            **base.model_dump(),
            comments=comments,
            child_tasks=child_briefs,
        )

    async def history(self, actor: User, task_id: int, *, limit: int = 100) -> TaskHistoryResponse:
        from app.modules.audit.repository import AuditRepository

        task = await self._repo.get_by_id(task_id)
        if task is None:
            raise NotFound(message="Задача не найдена")
        await self._ensure_task_visible(actor, task)
        rows = await AuditRepository(self._session).list_for_entity(
            entity_type="task",
            entity_id=task_id,
            limit=max(1, min(limit, 200)),
        )
        actors = await self._users_map({row.actor_id for row in rows if row.actor_id is not None})
        items = [
            TaskHistoryItem(
                id=row.id,
                action=row.action.value if hasattr(row.action, "value") else str(row.action),
                summary=format_task_history_summary(
                    row.action.value if hasattr(row.action, "value") else str(row.action),
                    dict(row.payload or {}),
                ),
                payload=dict(row.payload or {}),
                created_at=row.created_at,
                actor=(
                    TaskUserBrief(id=actors[row.actor_id].id, full_name=actors[row.actor_id].full_name)
                    if row.actor_id in actors
                    else None
                ),
            )
            for row in rows
        ]
        return TaskHistoryResponse(items=items)

    async def list_comments(self, actor: User, task_id: int) -> TaskCommentListResponse:
        detail = await self.get_task(actor, task_id)
        return TaskCommentListResponse(items=detail.comments)

    async def add_comment(
        self,
        actor: User,
        task_id: int,
        body: str,
        *,
        file_ids: list[int] | None = None,
    ) -> TaskCommentResponse:
        task = await self._repo.get_by_id(task_id)
        if task is None:
            raise NotFound(message="Задача не найдена")
        await self._ensure_task_visible(actor, task)
        row = await self._add_comment_row(task, actor, body, file_ids=file_ids)
        if row is None:
            raise ValidationError(message="Напишите комментарий или прикрепите файл")
        await publish(
            TASK_UPDATED,
            {**self._event_payload(task), "comment_id": row.id},
            scope={"user_id": task.assignee_id},
        )
        await publish(
            TASK_UPDATED,
            {**self._event_payload(task), "comment_id": row.id},
            scope={"user_id": task.created_by},
        )
        return TaskCommentResponse(
            id=row.id,
            task_id=row.task_id,
            author_id=row.author_id,
            body=row.body,
            created_at=row.created_at,
            author=TaskUserBrief(id=actor.id, full_name=actor.full_name),
        )

    async def attach_files(self, actor: User, task_id: int, file_ids: list[int]) -> TaskResponse:
        task = await self._repo.get_by_id(task_id)
        if task is None:
            raise NotFound(message="Задача не найдена")
        await self._ensure_task_visible(actor, task)
        if task.status in {TaskStatus.CLOSED.value, TaskStatus.DELETED.value}:
            raise ValidationError(message="К закрытой задаче файлы не добавить")
        await self._attach_files(task.id, file_ids)
        await self._write_history(
            actor,
            task,
            AuditAction.TASK_UPDATE,
            {"kind": "files", "count": len(file_ids)},
        )
        return (await self._build_responses([task]))[0]

    async def handoff(self, actor: User, task_id: int, body) -> TaskResponse:
        from app.modules.tasks.schemas import TaskHandoffRequest

        if not isinstance(body, TaskHandoffRequest):
            body = TaskHandoffRequest.model_validate(body)
        task = await self._repo.get_by_id(task_id)
        if task is None:
            raise NotFound(message="Задача не найдена")
        await self._ensure_task_visible(actor, task)
        if task.status not in {
            TaskStatus.NEW.value,
            TaskStatus.OPEN.value,
            TaskStatus.DONE_PENDING.value,
        }:
            raise ValidationError(message="Эту задачу уже нельзя передать")
        if not await self._can_handoff(actor, task):
            raise PermissionDenied(
                message="Сменить исполнителя может постановщик, исполнитель, админ или старший группы",
            )

        next_user = await self._ensure_active_assignee(body.user_id)
        await self._ensure_assignee_target_allowed(actor, task, next_user)
        if next_user.id == task.assignee_id and body.action in {"add", "transfer"}:
            raise ValidationError(message="Этот сотрудник уже исполнитель")
        if body.action != "follow_up" and next_user.id == actor.id and actor.id == task.assignee_id:
            raise ValidationError(message="Выберите другого сотрудника")

        comment = (body.comment or "").strip()
        await self._add_comment_row(task, actor, comment, file_ids=body.file_ids)

        if body.action == "add":
            await self._add_collaborator(task, next_user.id, added_by=actor.id)
            note = (
                f"{actor.full_name} добавил(а) соисполнителя: {next_user.full_name}"
            )
            if not comment:
                await self._add_comment_row(task, actor, note)
            await self._write_history(
                actor,
                task,
                AuditAction.TASK_HANDOFF,
                {
                    "kind": "add",
                    "user_id": next_user.id,
                    "user_name": next_user.full_name,
                },
            )
            await publish(TASK_CREATED, self._event_payload(task), scope={"user_id": next_user.id})
            await publish(
                TASK_UPDATED,
                self._event_payload(task),
                scope={"department_id": task.department_id},
            )
            return (await self._build_responses([task]))[0]

        if body.action == "transfer":
            previous_id = task.assignee_id
            await self._add_collaborator(task, previous_id, added_by=actor.id)
            from app.modules.db.models.department_task_collaborator import (
                DepartmentTaskCollaborator,
            )

            current_collab = await self._session.get(
                DepartmentTaskCollaborator,
                (task.id, next_user.id),
            )
            if current_collab is not None:
                await self._session.delete(current_collab)
            task.assignee_id = next_user.id
            if task.status == TaskStatus.DONE_PENDING.value:
                task.status = TaskStatus.OPEN.value
                task.completed_at = None
                task.completed_by = None
            elif task.status == TaskStatus.NEW.value:
                task.status = TaskStatus.OPEN.value
            task = await self._repo.save(task)
            if not comment:
                await self._add_comment_row(
                    task,
                    actor,
                    f"{actor.full_name} передал(а) задачу {next_user.full_name}",
                )
            await self._write_history(
                actor,
                task,
                AuditAction.TASK_HANDOFF,
                {
                    "kind": "transfer",
                    "user_id": next_user.id,
                    "user_name": next_user.full_name,
                    "from": previous_id,
                },
            )
            await publish(TASK_CREATED, self._event_payload(task), scope={"user_id": next_user.id})
            await publish(
                TASK_UPDATED,
                self._event_payload(task),
                scope={"department_id": task.department_id},
            )
            return (await self._build_responses([task]))[0]

        title = (body.follow_up_title or "").strip() or f"Продолжение: {task.title}"
        child = DepartmentTask(
            department_id=task.department_id,
            title=title,
            description=(body.follow_up_description or "").strip() or None,
            task_type=task.task_type,
            status=TaskStatus.OPEN.value,
            source="follow_up",
            opt_unit_id=task.opt_unit_id,
            opt_requirement_id=task.opt_requirement_id,
            chat_id=task.chat_id,
            lead_id=task.lead_id,
            parent_task_id=task.id,
            created_by=actor.id,
            assignee_id=next_user.id,
            due_at=body.follow_up_due_at,
        )
        child = await self._repo.create(child)
        await self._attach_files(child.id, body.file_ids)
        await self._write_history(
            actor,
            child,
            AuditAction.TASK_CREATE,
            {
                "kind": "create",
                "title": child.title,
                "assignee_id": next_user.id,
                "assignee_name": next_user.full_name,
                "parent_task_id": task.id,
            },
        )
        await self._write_history(
            actor,
            task,
            AuditAction.TASK_HANDOFF,
            {
                "kind": "follow_up",
                "user_id": next_user.id,
                "user_name": next_user.full_name,
                "child_title": child.title,
                "child_id": child.id,
            },
        )
        if not comment:
            await self._add_comment_row(
                task,
                actor,
                f"{actor.full_name} поставил(а) связанную задачу «{child.title}» для {next_user.full_name}",
            )
        payload = self._event_payload(child)
        await publish(TASK_CREATED, payload, scope={"user_id": child.assignee_id})
        await publish(TASK_CREATED, payload, scope={"department_id": child.department_id})
        return (await self._build_responses([task]))[0]

    async def notify_assignee(self, actor: User, task_id: int, message: str | None) -> dict:
        task = await self._repo.get_by_id(task_id)
        if task is None:
            raise NotFound(message="Задача не найдена")
        await self._ensure_task_visible(actor, task)
        role = self._role(actor)
        can = (
            actor.id == task.created_by
            or role in {UserRole.ADMIN, UserRole.SENIOR, UserRole.GROUP_SENIOR, UserRole.CHIEF_ACCOUNTANT}
        )
        if not can:
            raise PermissionDenied(message="Нельзя уведомить исполнителя")
        if actor.id == task.assignee_id and role not in {
            UserRole.ADMIN,
            UserRole.SENIOR,
            UserRole.GROUP_SENIOR,
            UserRole.CHIEF_ACCOUNTANT,
        }:
            raise PermissionDenied(message="Нельзя уведомить самого себя")
        payload = {
            **self._event_payload(task),
            "notify_kind": "assignee",
            "from_user_id": actor.id,
            "from_user_name": actor.full_name,
            "message": (message or "").strip() or None,
            "title": task.title,
        }
        await publish(TASK_NOTIFY, payload, scope={"user_id": task.assignee_id})
        return {"ok": True}

    async def notify_creator(self, actor: User, task_id: int, message: str | None) -> dict:
        task = await self._repo.get_by_id(task_id)
        if task is None:
            raise NotFound(message="Задача не найдена")
        await self._ensure_task_visible(actor, task)
        if not await self._is_working_on(actor, task) and not self._is_senior_or_admin(actor):
            raise PermissionDenied(message="Нельзя уведомить постановщика")
        if actor.id == task.created_by and not self._is_senior_or_admin(actor):
            raise PermissionDenied(message="Нельзя уведомить самого себя")
        payload = {
            **self._event_payload(task),
            "notify_kind": "creator",
            "from_user_id": actor.id,
            "from_user_name": actor.full_name,
            "message": (message or "").strip() or None,
            "title": task.title,
        }
        await publish(TASK_NOTIFY, payload, scope={"user_id": task.created_by})
        return {"ok": True}

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

    async def list_client_requirement_units(self, actor: User):
        from app.modules.db.models.opt_accountant_unit_assignment import (
            OptAccountantUnitAssignment,
        )
        from app.modules.db.models.opt_unit import OptUnit
        from app.modules.tasks.schemas import (
            ClientRequirementUnitListResponse,
            ClientRequirementUnitOption,
        )

        units_result = await self._session.execute(
            select(OptUnit)
            .where(OptUnit.is_active.is_(True))
            .order_by(OptUnit.name, OptUnit.inn),
        )
        units = list(units_result.scalars().all())
        assign_result = await self._session.execute(
            select(OptAccountantUnitAssignment).order_by(OptAccountantUnitAssignment.id),
        )
        accountant_by_unit: dict[int, int] = {}
        for row in assign_result.scalars().all():
            accountant_by_unit.setdefault(int(row.unit_id), int(row.user_id))

        accountants_result = await self._session.execute(
            select(User)
            .where(User.status == UserStatus.ACTIVE)
            .order_by(User.full_name)
            .limit(500),
        )
        people = list(accountants_result.scalars().all())
        people.sort(
            key=lambda u: (0 if u.id == actor.id else 1, (u.full_name or "").casefold()),
        )
        assignees = [
            ClientRequirementAccountantOption(
                id=user.id,
                full_name=user.full_name or f"user #{user.id}",
                role=user.role.value if hasattr(user.role, "value") else str(user.role),
            )
            for user in people
        ]
        items = [
            ClientRequirementUnitOption(
                id=u.id,
                inn=u.inn,
                name=u.name,
                accountant_user_id=accountant_by_unit.get(int(u.id)),
            )
            for u in units
        ]
        return ClientRequirementUnitListResponse(
            items=items,
            accountants=assignees,
            assignees=assignees,
        )

    async def create_client_requirement(
        self,
        actor: User,
        body,
    ) -> TaskResponse:
        from app.modules.db.models.department_task_file import DepartmentTaskFile
        from app.modules.db.models.opt_accountant_unit_assignment import (
            OptAccountantUnitAssignment,
        )
        from app.modules.db.models.opt_unit import OptUnit
        from app.modules.tasks.schemas import ClientRequirementCreateRequest

        if not isinstance(body, ClientRequirementCreateRequest):
            body = ClientRequirementCreateRequest.model_validate(body)

        unit = await self._session.get(OptUnit, body.unit_id)
        if unit is None or not unit.is_active:
            raise ValidationError(message="Лавка не найдена")

        assignee_id = body.assignee_id
        if assignee_id is None:
            result = await self._session.execute(
                select(OptAccountantUnitAssignment)
                .where(OptAccountantUnitAssignment.unit_id == unit.id)
                .order_by(OptAccountantUnitAssignment.id)
                .limit(1),
            )
            assignment = result.scalar_one_or_none()
            if assignment is None:
                raise ValidationError(
                    message="Выберите исполнителя или привяжите бухгалтера к лавке",
                )
            assignee_id = int(assignment.user_id)

        assignee = await self._ensure_active_assignee(assignee_id)
        dept_id = await self._resolve_department_for_task(actor, assignee)

        due_at = body.due_at
        if due_at is None:
            due_at = datetime.now(UTC) + timedelta(days=3)

        row = DepartmentTask(
            department_id=dept_id,
            title=body.title.strip(),
            description=body.description.strip() if body.description else None,
            task_type=TaskType.HIGH.value,
            status=TaskStatus.NEW.value,
            source="client_request",
            opt_unit_id=unit.id,
            chat_id=body.chat_id,
            lead_id=body.lead_id,
            created_by=actor.id,
            assignee_id=assignee.id,
            due_at=due_at,
        )
        row = await self._repo.create(row)
        for fid in body.file_ids or []:
            self._session.add(DepartmentTaskFile(task_id=row.id, file_id=int(fid)))
        await self._session.flush()
        await self._write_history(
            actor,
            row,
            AuditAction.TASK_CREATE,
            {
                "kind": "create",
                "title": row.title,
                "assignee_id": assignee.id,
                "assignee_name": assignee.full_name,
                "source": "client_request",
            },
        )
        response = (await self._build_responses([row]))[0]
        payload = self._event_payload(row)
        await publish(TASK_CREATED, payload, scope={"user_id": row.assignee_id})
        await publish(TASK_CREATED, payload, scope={"department_id": row.department_id})
        # Notify chief/admin via department broadcast already; they use alerts poll.
        return response

    async def list_for_chat(self, actor: User, chat_id: int) -> TaskListResponse:
        result = await self._session.execute(
            select(DepartmentTask)
            .where(
                DepartmentTask.chat_id == chat_id,
                DepartmentTask.source == "client_request",
                DepartmentTask.status != TaskStatus.DELETED.value,
            )
            .order_by(DepartmentTask.created_at.desc())
            .limit(50),
        )
        rows = list(result.scalars().all())
        # creator or assignee or senior/admin can see
        role = self._role(actor)
        visible: list[DepartmentTask] = []
        for row in rows:
            if (
                row.created_by == actor.id
                or row.assignee_id == actor.id
                or role in {UserRole.ADMIN, UserRole.CHIEF_ACCOUNTANT, UserRole.SENIOR, UserRole.GROUP_SENIOR}
            ):
                visible.append(row)
        items = await self._build_responses(visible)
        return TaskListResponse(items=items, total=len(items))

    async def alerts(self, actor: User):
        from app.modules.tasks.schemas import TaskAlertsResponse

        now = datetime.now(UTC)
        role = self._role(actor)
        due_soon = overdue = unacked_fns = client_due = 0

        if role in {UserRole.USER, UserRole.GROUP_SENIOR, UserRole.SENIOR, UserRole.LAWYER}:
            mine = await self._repo.list_for_assignee(actor.id, include_closed=False)
            for task in mine:
                is_overdue, is_due_soon = self._task_flags(task, now)
                if is_overdue:
                    overdue += 1
                elif is_due_soon:
                    due_soon += 1
                if (
                    task.status == TaskStatus.NEW.value
                    and (getattr(task, "source", None) or "") == "fns_requirement"
                ):
                    unacked_fns += 1

        if role in {UserRole.ACCOUNTANT, UserRole.CHIEF_ACCOUNTANT, UserRole.ADMIN}:
            if role == UserRole.ACCOUNTANT:
                rows = await self._repo.list_for_assignee(actor.id, include_closed=False)
            else:
                # chief/admin: all active client_request + own
                result = await self._session.execute(
                    select(DepartmentTask).where(
                        DepartmentTask.status.in_(
                            [TaskStatus.NEW.value, TaskStatus.OPEN.value],
                        ),
                    ).limit(500),
                )
                rows = list(result.scalars().all())
            for task in rows:
                is_overdue, is_due_soon = self._task_flags(task, now)
                if (getattr(task, "source", None) or "") == "client_request" or role == UserRole.ACCOUNTANT:
                    if is_overdue or is_due_soon:
                        client_due += 1
                if is_overdue:
                    overdue += 1
                elif is_due_soon:
                    due_soon += 1

        blink = bool(unacked_fns or client_due or overdue or due_soon)
        # Managers blink primarily on unacked FNS; accountants/admin on due client/tasks
        if role in {UserRole.USER, UserRole.GROUP_SENIOR}:
            blink = bool(unacked_fns or overdue or due_soon)
        elif role in {UserRole.ACCOUNTANT, UserRole.CHIEF_ACCOUNTANT, UserRole.ADMIN}:
            blink = bool(client_due or overdue)

        return TaskAlertsResponse(
            blink=blink,
            due_soon=due_soon,
            overdue=overdue,
            unacked_fns=unacked_fns,
            client_due=client_due,
        )
