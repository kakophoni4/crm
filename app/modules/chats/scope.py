from __future__ import annotations

from sqlalchemy import ColumnElement, or_

from app.modules.db.models.chat import Chat
from app.modules.db.models.enums import UserRole
from app.modules.db.models.user import User
from app.modules.rbac.permissions import Permission
from app.modules.rbac.role_map import has_permission
from app.modules.rbac.scope import (
    SCOPE_ALL,
    ScopeContext,
    visible_department_ids,
    visible_group_ids,
)
from app.shared.settings import settings


def resolve_chats_read_permission(actor: User) -> Permission:
    role = actor.role if isinstance(actor.role, UserRole) else UserRole(str(actor.role))
    if has_permission(role, Permission.CHATS_READ_ALL):
        return Permission.CHATS_READ_ALL
    if has_permission(role, Permission.CHATS_READ_DEPARTMENT):
        return Permission.CHATS_READ_DEPARTMENT
    if has_permission(role, Permission.CHATS_READ_GROUP):
        return Permission.CHATS_READ_GROUP
    return Permission.CHATS_READ_OWN


def _user_group_chat_clause(ctx: ScopeContext) -> ColumnElement[bool] | None:
    group_ids = visible_group_ids(ctx)
    if group_ids == SCOPE_ALL:
        return None
    if not isinstance(group_ids, set) or not group_ids:
        return Chat.id == -1
    return Chat.assigned_group_id.in_(group_ids)


def chat_visibility_clause(ctx: ScopeContext, perm: Permission) -> ColumnElement[bool] | None:
    if perm == Permission.CHATS_READ_ALL:
        return None

    actor = ctx.actor

    if perm == Permission.CHATS_READ_OWN:
        if settings.ownership_v2:
            return _user_group_chat_clause(ctx)
        return Chat.assigned_user_id == actor.id

    if perm == Permission.CHATS_READ_GROUP:
        return _user_group_chat_clause(ctx)

    if perm == Permission.CHATS_READ_DEPARTMENT:
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

    return Chat.id == -1


def can_view_chat(ctx: ScopeContext, chat: Chat) -> bool:
    perm = resolve_chats_read_permission(ctx.actor)
    clause = chat_visibility_clause(ctx, perm)
    if clause is None:
        return True
    if perm == Permission.CHATS_READ_OWN:
        if settings.ownership_v2:
            group_ids = visible_group_ids(ctx)
            if group_ids == SCOPE_ALL:
                return True
            if not isinstance(group_ids, set):
                return False
            return chat.assigned_group_id in group_ids if chat.assigned_group_id else False
        return chat.assigned_user_id == ctx.actor.id
    if perm == Permission.CHATS_READ_GROUP:
        group_ids = visible_group_ids(ctx)
        if group_ids == SCOPE_ALL:
            return True
        if not isinstance(group_ids, set):
            return False
        return chat.assigned_group_id in group_ids if chat.assigned_group_id else False
    if perm == Permission.CHATS_READ_DEPARTMENT:
        dept_ids = visible_department_ids(ctx)
        if dept_ids == SCOPE_ALL:
            return True
        if not isinstance(dept_ids, set):
            return False
        dept_user_ids = set(ctx.department_user_ids) | {ctx.actor.id}
        dept_group_ids = set(ctx.department_group_ids)
        return (
            chat.assigned_department_id in dept_ids
            or chat.assigned_user_id in dept_user_ids
            or (chat.assigned_group_id in dept_group_ids if chat.assigned_group_id else False)
        )
    return False


def visible_chat_ids(ctx: ScopeContext) -> str:
    """Returns resolved read permission slug for repository scoping."""
    return resolve_chats_read_permission(ctx.actor).value


def chat_department_id(chat: Chat) -> int | None:
    if chat.assigned_department_id is not None:
        return chat.assigned_department_id
    if chat.contact is not None and chat.contact.assigned_department_id is not None:
        return chat.contact.assigned_department_id
    return None
