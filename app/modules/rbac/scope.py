from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from app.modules.db.models.enums import UserRole
from app.modules.db.models.user import User

SCOPE_ALL: Literal["ALL"] = "ALL"
ScopeResult = set[int] | Literal["ALL"]


@dataclass(frozen=True)
class ScopeContext:
    """Pure scope input: actor plus preloaded membership (no I/O)."""

    actor: User
    actor_group_ids: frozenset[int] = field(default_factory=frozenset)
    group_member_ids: frozenset[int] = field(default_factory=frozenset)
    department_user_ids: frozenset[int] = field(default_factory=frozenset)
    department_senior_id: int | None = None
    department_group_ids: frozenset[int] = field(default_factory=frozenset)


def visible_user_ids(ctx: ScopeContext) -> ScopeResult:
    actor = ctx.actor
    role = actor.role if isinstance(actor.role, UserRole) else UserRole(str(actor.role))

    if role == UserRole.ADMIN:
        return SCOPE_ALL

    if role == UserRole.SENIOR:
        if actor.department_id is None:
            return {actor.id}
        return set(ctx.department_user_ids) | {actor.id}

    # user (operator)
    visible: set[int] = {actor.id}
    visible.update(ctx.group_member_ids)
    if ctx.department_senior_id is not None:
        visible.add(ctx.department_senior_id)
    return visible


def visible_group_ids(ctx: ScopeContext) -> ScopeResult:
    actor = ctx.actor
    role = actor.role if isinstance(actor.role, UserRole) else UserRole(str(actor.role))

    if role == UserRole.ADMIN:
        return SCOPE_ALL

    if role == UserRole.SENIOR:
        if actor.department_id is None:
            return set()
        return set(ctx.department_group_ids)

    if ctx.actor_group_ids:
        return set(ctx.actor_group_ids)

    if actor.group_id is not None:
        return {actor.group_id}
    return set()


def visible_department_ids(ctx: ScopeContext) -> ScopeResult:
    actor = ctx.actor
    role = actor.role if isinstance(actor.role, UserRole) else UserRole(str(actor.role))

    if role == UserRole.ADMIN:
        return SCOPE_ALL

    if actor.department_id is not None:
        return {actor.department_id}
    return set()


def can_act_on_user(ctx: ScopeContext, target: User) -> bool:
    """Whether actor may transfer/takeover/edit the target user (scope + role rules)."""
    actor = ctx.actor
    if actor.id == target.id:
        return True

    role = actor.role if isinstance(actor.role, UserRole) else UserRole(str(actor.role))
    target_role = target.role if isinstance(target.role, UserRole) else UserRole(str(target.role))

    if role == UserRole.ADMIN:
        return True

    if role == UserRole.SENIOR:
        if actor.department_id is None or target.department_id != actor.department_id:
            return False
        return not (target_role == UserRole.SENIOR and target.id != actor.id)

    visible = visible_user_ids(ctx)
    if not isinstance(visible, set):
        return False
    return target.id in visible
