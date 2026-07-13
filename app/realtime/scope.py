from __future__ import annotations

from dataclasses import dataclass

from app.modules.db.models.enums import UserRole
from app.modules.rbac.scope import SCOPE_ALL, ScopeContext, visible_user_ids
from app.realtime.events import Event
from app.realtime.topics import ADMIN_ONLY_TOPICS


@dataclass(frozen=True)
class WsScope:
    user_id: int
    role: UserRole
    department_id: int | None
    group_id: int | None
    actor_group_ids: frozenset[int]
    department_group_ids: frozenset[int]
    visible_user_ids: frozenset[int] | None  # None = all users (admin)

    @classmethod
    def from_context(cls, ctx: ScopeContext) -> WsScope:
        actor_role = ctx.actor.role
        role = actor_role if isinstance(actor_role, UserRole) else UserRole(str(actor_role))
        visible = visible_user_ids(ctx)
        visible_frozen = None if visible == SCOPE_ALL else frozenset(visible)
        return cls(
            user_id=ctx.actor.id,
            role=role,
            department_id=ctx.actor.department_id,
            group_id=ctx.actor.group_id,
            actor_group_ids=frozenset(ctx.actor_group_ids),
            department_group_ids=frozenset(ctx.department_group_ids),
            visible_user_ids=visible_frozen,
        )


def event_visible(ws_scope: WsScope, event: Event) -> bool:
    if event.topic in ADMIN_ONLY_TOPICS:
        return ws_scope.role == UserRole.ADMIN

    if ws_scope.role == UserRole.ADMIN:
        return True

    scope = event.scope
    payload = event.payload

    if "user_id" in scope:
        target_id = int(scope["user_id"])
        if ws_scope.role == UserRole.USER:
            return target_id == ws_scope.user_id
        if ws_scope.visible_user_ids is None:
            return True
        return target_id in ws_scope.visible_user_ids

    if "department_id" in scope:
        dept_id = int(scope["department_id"])
        if ws_scope.role == UserRole.SENIOR:
            return ws_scope.department_id == dept_id
        # Chat events often include both department_id and group_id.
        # Operators must not be dropped by department_id — fall through to group_id.
        if "group_id" not in scope:
            return False

    if "group_id" in scope:
        target_group = int(scope["group_id"])
        if ws_scope.role == UserRole.SENIOR:
            return target_group in ws_scope.department_group_ids
        if ws_scope.role in (UserRole.USER, UserRole.GROUP_SENIOR):
            if ws_scope.group_id == target_group:
                return True
            return target_group in ws_scope.actor_group_ids
        return False

    if ws_scope.role == UserRole.USER:
        for key in ("sender_user_id", "from_user_id", "assigned_user_id", "to_user_id"):
            value = payload.get(key)
            if value is not None and int(value) == ws_scope.user_id:
                return True
        return False

    if ws_scope.role == UserRole.GROUP_SENIOR:
        if "group_id" in payload:
            return int(payload["group_id"]) in ws_scope.actor_group_ids
        return not scope

    if ws_scope.role == UserRole.SENIOR:
        if ws_scope.department_id is None:
            return False
        dept_in_payload = payload.get("department_id")
        if dept_in_payload is not None:
            return int(dept_in_payload) == ws_scope.department_id
        return not scope

    return False
