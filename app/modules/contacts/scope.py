from __future__ import annotations

from sqlalchemy import ColumnElement, exists, or_, select

from app.modules.db.models.chat import Chat
from app.modules.db.models.contact import Contact
from app.modules.db.models.contact_group_assignment import ContactGroupAssignment
from app.modules.db.models.enums import UserRole
from app.modules.rbac.scope import (
    SCOPE_ALL,
    ScopeContext,
    ScopeResult,
    visible_group_ids,
    visible_user_ids,
)


def _group_contact_clause(group_ids: set[int]) -> ColumnElement[bool]:
    chat_in_group = exists(
        select(1).where(
            Chat.contact_id == Contact.id,
            Chat.assigned_group_id.in_(group_ids),
        ),
    )
    assignment_in_group = exists(
        select(1).where(
            ContactGroupAssignment.contact_id == Contact.id,
            ContactGroupAssignment.group_id.in_(group_ids),
        ),
    )
    return or_(chat_in_group, assignment_in_group)


def contact_visibility_clause(ctx: ScopeContext) -> ColumnElement[bool] | None:
    role = ctx.actor.role if isinstance(ctx.actor.role, UserRole) else UserRole(str(ctx.actor.role))
    if role == UserRole.ADMIN:
        return None

    group_ids = visible_group_ids(ctx)
    if group_ids == SCOPE_ALL:
        return None
    if not isinstance(group_ids, set) or not group_ids:
        return Contact.id == -1
    return _group_contact_clause(group_ids)


def contact_scope_filter(scope: ScopeResult, actor_id: int) -> bool:
    if scope == SCOPE_ALL:
        return True
    if not isinstance(scope, set):
        return False
    return actor_id in scope


def actor_can_read_audit(ctx: ScopeContext, actor_id: int | None) -> bool:
    if actor_id is None:
        return False
    scope = visible_user_ids(ctx)
    if scope == SCOPE_ALL:
        return True
    if not isinstance(scope, set):
        return False
    return actor_id in scope


def actor_is_admin(ctx: ScopeContext) -> bool:
    role = ctx.actor.role if isinstance(ctx.actor.role, UserRole) else UserRole(str(ctx.actor.role))
    return role == UserRole.ADMIN
