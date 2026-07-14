from __future__ import annotations

from sqlalchemy import Select, and_, exists, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.chats.schemas import (
    QuickReplyTemplateCreateRequest,
    QuickReplyTemplateListResponse,
    QuickReplyTemplateResponse,
    QuickReplyTemplateUpdateRequest,
)
from app.modules.contacts.scope_loader import ScopeLoader
from app.modules.db.models.enums import UserRole
from app.modules.db.models.group import Group
from app.modules.db.models.quick_reply_template import QuickReplyTemplate
from app.modules.db.models.quick_reply_template_hidden import QuickReplyTemplateHidden
from app.modules.db.models.user import User
from app.modules.rbac.scope import SCOPE_ALL, visible_department_ids, visible_group_ids
from app.shared.exceptions import NotFound, PermissionDenied, ValidationError


class QuickReplyTemplateService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_templates(
        self,
        actor: User,
        *,
        q: str | None,
        department_id: int | None,
        group_id: int | None,
        scope: str | None,
        limit: int,
        include_inactive: bool = False,
    ) -> QuickReplyTemplateListResponse:
        visible_depts, visible_groups = await self._visible_scope(actor)
        self._ensure_scope_filter_visible(
            department_id=department_id,
            group_id=group_id,
            visible_depts=visible_depts,
            visible_groups=visible_groups,
        )

        stmt = select(QuickReplyTemplate).order_by(
            QuickReplyTemplate.usage_count.desc(),
            QuickReplyTemplate.updated_at.desc(),
        )
        stmt = self._apply_visible_scope(stmt, actor, visible_depts, visible_groups, scope)
        stmt = stmt.where(
            ~exists().where(
                QuickReplyTemplateHidden.template_id == QuickReplyTemplate.id,
                QuickReplyTemplateHidden.user_id == actor.id,
            ),
        )
        if not include_inactive:
            stmt = stmt.where(QuickReplyTemplate.is_active.is_(True))
        if department_id is not None:
            stmt = stmt.where(QuickReplyTemplate.department_id == department_id)
        if group_id is not None:
            stmt = stmt.where(QuickReplyTemplate.group_id == group_id)
        if q:
            needle = f"%{q.strip()}%"
            stmt = stmt.where(
                or_(
                    QuickReplyTemplate.title.ilike(needle),
                    QuickReplyTemplate.body.ilike(needle),
                ),
            )
        stmt = stmt.limit(max(1, min(limit, 50)))
        result = await self._session.execute(stmt)
        return QuickReplyTemplateListResponse(
            items=[self._to_response(row) for row in result.scalars().all()],
        )

    async def create_template(
        self,
        actor: User,
        body: QuickReplyTemplateCreateRequest,
    ) -> QuickReplyTemplateResponse:
        if body.scope == "personal":
            row = QuickReplyTemplate(
                title=body.title.strip(),
                body=body.body.strip(),
                department_id=None,
                group_id=None,
                owner_user_id=actor.id,
                is_active=body.is_active,
                created_by=actor.id,
                updated_by=actor.id,
            )
        else:
            department_id, group_id = await self._resolve_scope(
                actor,
                body.department_id,
                body.group_id,
            )
            row = QuickReplyTemplate(
                title=body.title.strip(),
                body=body.body.strip(),
                department_id=department_id,
                group_id=group_id,
                owner_user_id=None,
                is_active=body.is_active,
                created_by=actor.id,
                updated_by=actor.id,
            )
        self._session.add(row)
        await self._session.commit()
        await self._session.refresh(row)
        return self._to_response(row)

    async def update_template(
        self,
        actor: User,
        template_id: int,
        body: QuickReplyTemplateUpdateRequest,
    ) -> QuickReplyTemplateResponse:
        row = await self._get_visible(actor, template_id)
        if row.owner_user_id is not None and row.owner_user_id != actor.id:
            raise PermissionDenied(message="Cannot edit another user's personal template")
        if body.title is not None:
            row.title = body.title.strip()
        if body.body is not None:
            row.body = body.body.strip()
        if row.owner_user_id is None and (
            body.department_id is not None or body.group_id is not None
        ):
            row.department_id, row.group_id = await self._resolve_scope(
                actor,
                body.department_id,
                body.group_id,
            )
        if body.is_active is not None:
            row.is_active = body.is_active
        row.updated_by = actor.id
        await self._session.commit()
        await self._session.refresh(row)
        return self._to_response(row)

    async def delete_template(self, actor: User, template_id: int) -> QuickReplyTemplateResponse:
        row = await self._get_visible(actor, template_id)
        if row.owner_user_id is not None and row.owner_user_id != actor.id:
            raise PermissionDenied(message="Cannot delete another user's personal template")
        response = self._to_response(row)
        await self._session.delete(row)
        await self._session.commit()
        return response

    async def hide_template(self, actor: User, template_id: int) -> QuickReplyTemplateResponse:
        row = await self._get_visible(actor, template_id)
        # Personal templates: hide == delete for owner.
        if row.owner_user_id == actor.id:
            response = self._to_response(row)
            await self._session.delete(row)
            await self._session.commit()
            return response
        await self._session.execute(
            insert(QuickReplyTemplateHidden)
            .values(template_id=row.id, user_id=actor.id)
            .on_conflict_do_nothing(
                index_elements=[
                    QuickReplyTemplateHidden.template_id,
                    QuickReplyTemplateHidden.user_id,
                ],
            ),
        )
        await self._session.commit()
        return self._to_response(row)

    async def track_use(self, actor: User, template_id: int) -> QuickReplyTemplateResponse:
        row = await self._get_visible(actor, template_id)
        row.usage_count += 1
        await self._session.commit()
        await self._session.refresh(row)
        return self._to_response(row)

    async def _visible_scope(self, actor: User) -> tuple[set[int] | str, set[int] | str]:
        ctx = await ScopeLoader(self._session).load(actor)
        return visible_department_ids(ctx), visible_group_ids(ctx)

    def _apply_visible_scope(
        self,
        stmt: Select[tuple[QuickReplyTemplate]],
        actor: User,
        visible_depts: set[int] | str,
        visible_groups: set[int] | str,
        scope: str | None,
    ) -> Select[tuple[QuickReplyTemplate]]:
        personal = QuickReplyTemplate.owner_user_id == actor.id
        if visible_depts == SCOPE_ALL or visible_groups == SCOPE_ALL:
            shared = QuickReplyTemplate.owner_user_id.is_(None)
        else:
            assert isinstance(visible_depts, set)
            assert isinstance(visible_groups, set)
            shared = and_(
                QuickReplyTemplate.owner_user_id.is_(None),
                or_(
                    QuickReplyTemplate.department_id.in_(visible_depts),
                    QuickReplyTemplate.group_id.in_(visible_groups),
                ),
            )

        normalized = (scope or "all").strip().lower()
        if normalized == "personal":
            return stmt.where(personal)
        if normalized == "shared":
            return stmt.where(shared)
        return stmt.where(or_(shared, personal))

    def _ensure_scope_filter_visible(
        self,
        *,
        department_id: int | None,
        group_id: int | None,
        visible_depts: set[int] | str,
        visible_groups: set[int] | str,
    ) -> None:
        if (
            department_id is not None
            and visible_depts != SCOPE_ALL
            and (not isinstance(visible_depts, set) or department_id not in visible_depts)
        ):
            raise PermissionDenied(message="Department outside scope")
        if (
            group_id is not None
            and visible_groups != SCOPE_ALL
            and (not isinstance(visible_groups, set) or group_id not in visible_groups)
        ):
            raise PermissionDenied(message="Group outside scope")

    async def _resolve_scope(
        self,
        actor: User,
        department_id: int | None,
        group_id: int | None,
    ) -> tuple[int, int | None]:
        role = actor.role if isinstance(actor.role, UserRole) else UserRole(str(actor.role))
        if group_id is not None:
            group = await self._session.get(Group, group_id)
            if group is None:
                raise ValidationError(message="group_id does not exist")
            department_id = group.department_id
        if department_id is None:
            department_id = actor.department_id
        if department_id is None:
            raise ValidationError(message="department_id is required")

        visible_depts, visible_groups = await self._visible_scope(actor)
        if role != UserRole.ADMIN:
            self._ensure_scope_filter_visible(
                department_id=department_id,
                group_id=group_id,
                visible_depts=visible_depts,
                visible_groups=visible_groups,
            )
        return department_id, group_id

    async def _get_visible(self, actor: User, template_id: int) -> QuickReplyTemplate:
        visible_depts, visible_groups = await self._visible_scope(actor)
        stmt = select(QuickReplyTemplate).where(QuickReplyTemplate.id == template_id)
        stmt = self._apply_visible_scope(stmt, actor, visible_depts, visible_groups, None)
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            raise NotFound(message="Quick reply template not found")
        return row

    def _to_response(self, row: QuickReplyTemplate) -> QuickReplyTemplateResponse:
        is_personal = row.owner_user_id is not None
        return QuickReplyTemplateResponse(
            id=row.id,
            title=row.title,
            body=row.body,
            department_id=row.department_id,
            group_id=row.group_id,
            owner_user_id=row.owner_user_id,
            scope="personal" if is_personal else "shared",
            is_active=row.is_active,
            usage_count=row.usage_count,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
