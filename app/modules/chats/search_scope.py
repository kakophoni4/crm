from __future__ import annotations

from enum import StrEnum

from sqlalchemy import ColumnElement, and_, exists, or_, select

from app.modules.db.models.chat import Chat
from app.modules.db.models.contact_group_assignment import ContactGroupAssignment
from app.modules.db.models.enums import UserRole
from app.modules.db.models.user import User
from app.modules.rbac.scope import (
    SCOPE_ALL,
    ScopeContext,
    visible_department_ids,
    visible_group_ids,
)
from app.shared.settings import settings


class ChatSearchScope(StrEnum):
    MINE = "mine"
    GROUP = "group"
    DEPARTMENT = "department"
    ALL = "all"


def default_search_scope(actor: User) -> ChatSearchScope:
    role = actor.role if isinstance(actor.role, UserRole) else UserRole(str(actor.role))
    if role == UserRole.ADMIN:
        return ChatSearchScope.ALL
    if role == UserRole.SENIOR:
        return ChatSearchScope.DEPARTMENT
    return ChatSearchScope.GROUP


def search_scope_clause(
    ctx: ScopeContext,
    scope: ChatSearchScope,
) -> ColumnElement[bool] | None:
    """Narrows FTS results within RBAC-visible chats."""
    actor = ctx.actor

    if scope == ChatSearchScope.ALL:
        return None

    if scope == ChatSearchScope.GROUP:
        group_ids = visible_group_ids(ctx)
        if group_ids == SCOPE_ALL:
            return None
        if not isinstance(group_ids, set) or not group_ids:
            return Chat.id == -1
        return Chat.assigned_group_id.in_(group_ids)

    if scope == ChatSearchScope.DEPARTMENT:
        dept_ids = visible_department_ids(ctx)
        if dept_ids == SCOPE_ALL:
            return None
        if not isinstance(dept_ids, set) or not dept_ids:
            return Chat.id == -1
        dept_user_ids = set(ctx.department_user_ids) | {actor.id}
        dept_group_ids = set(ctx.department_group_ids)
        clauses = [
            Chat.assigned_department_id.in_(dept_ids),
            Chat.assigned_user_id.in_(dept_user_ids),
        ]
        if dept_group_ids:
            clauses.append(Chat.assigned_group_id.in_(dept_group_ids))
        return or_(*clauses)

    if scope == ChatSearchScope.MINE:
        if settings.ownership_v2 and actor.group_id is not None:
            assignment_exists = exists(
                select(1).where(
                    ContactGroupAssignment.contact_id == Chat.contact_id,
                    ContactGroupAssignment.group_id == Chat.assigned_group_id,
                    ContactGroupAssignment.owner_user_id == actor.id,
                ),
            )
            return and_(
                Chat.assigned_group_id == actor.group_id,
                assignment_exists,
            )
        return Chat.assigned_user_id == actor.id

    return Chat.id == -1
