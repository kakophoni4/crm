"""Role-based access control: permissions, role map, scope."""

from app.modules.rbac.permissions import Permission
from app.modules.rbac.role_map import (
    ROLE_PERMISSIONS,
    has_all_permissions,
    has_any_permission,
    has_permission,
)
from app.modules.rbac.scope import (
    SCOPE_ALL,
    ScopeContext,
    can_act_on_user,
    visible_department_ids,
    visible_group_ids,
    visible_user_ids,
)

__all__ = [
    "ROLE_PERMISSIONS",
    "SCOPE_ALL",
    "Permission",
    "ScopeContext",
    "can_act_on_user",
    "has_all_permissions",
    "has_any_permission",
    "has_permission",
    "visible_department_ids",
    "visible_group_ids",
    "visible_user_ids",
]
