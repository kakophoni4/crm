from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends

from app.modules.db.models.user import User
from app.modules.rbac.permissions import Permission
from app.modules.rbac.role_map import has_all_permissions, has_any_permission, has_permission
from app.shared.exceptions import PermissionDenied
from app.shared.security.deps import current_user

__all__ = [
    "has_all_permissions",
    "has_any_permission",
    "has_permission",
    "requires_all_permissions",
    "requires_permission",
]


def requires_permission(*perms: Permission) -> Callable[..., Awaitable[User]]:
    async def dep(user: Annotated[User, Depends(current_user)]) -> User:
        if not has_any_permission(user.role, perms):
            raise PermissionDenied(
                details={"required": [permission.value for permission in perms]},
            )
        return user

    return dep


def requires_all_permissions(*perms: Permission) -> Callable[..., Awaitable[User]]:
    async def dep(user: Annotated[User, Depends(current_user)]) -> User:
        if not has_all_permissions(user.role, perms):
            raise PermissionDenied(
                details={"required": [permission.value for permission in perms]},
            )
        return user

    return dep
