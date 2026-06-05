from __future__ import annotations

import pytest

from app.modules.db.models.enums import UserRole
from app.modules.rbac.permissions import ALL_PERMISSIONS, Permission
from app.modules.rbac.role_map import ROLE_PERMISSIONS, has_permission

# Expected grants copied from docs/RBAC_MATRIX.md §3.

_USER_EXPECTED: frozenset[Permission] = frozenset(
    {
        Permission.PROFILE_PASSWORD_UPDATE,
        Permission.PROFILE_FULL_NAME_UPDATE,
        Permission.PROFILE_PRESENCE_UPDATE,
        Permission.PROFILE_AVAILABILITY_UPDATE,
        Permission.USERS_READ,
        Permission.USERS_READ_GROUP,
        Permission.GROUPS_READ,
        Permission.GROUPS_READ_OWN,
        Permission.DEPARTMENTS_READ,
        Permission.CHATS_READ_OWN,
        Permission.CHATS_WRITE,
        Permission.CHATS_STATUS_UPDATE,
        Permission.CHATS_TRANSFER_REQUEST,
        Permission.CHATS_TRANSFER_CANCEL,
        Permission.CHATS_ARCHIVE,
        Permission.CONTACTS_READ,
        Permission.CONTACTS_READ_TELEGRAM_USERNAME,
        Permission.CONTACTS_CREATE,
        Permission.CONTACTS_UPDATE,
        Permission.CONTACTS_AUDIT_READ,
        Permission.BOTS_READ,
        Permission.STATUSES_READ,
        Permission.AUDIT_READ_OWN,
        Permission.FILES_UPLOAD,
        Permission.FILES_DOWNLOAD,
    }
)

_USER_DENIED: frozenset[Permission] = ALL_PERMISSIONS - _USER_EXPECTED

_SENIOR_EXPECTED: frozenset[Permission] = _USER_EXPECTED - {Permission.CHATS_READ_OWN} | frozenset(
    {
        Permission.USERS_CREATE_IN_DEP,
        Permission.USERS_UPDATE,
        Permission.USERS_UPDATE_GROUP_TRANSFER,
        Permission.USERS_PASSWORD_RESET,
        Permission.USERS_FORCE_LOGOUT,
        Permission.USERS_DEACTIVATE,
        Permission.USERS_DELETION_REQUEST_CREATE,
        Permission.USERS_DELETION_REQUEST_READ,
        Permission.GROUPS_CREATE_IN_DEP,
        Permission.GROUPS_UPDATE,
        Permission.GROUPS_DELETE,
        Permission.CHATS_READ_DEPARTMENT,
        Permission.CHATS_TRANSFER_APPROVE,
        Permission.CHATS_TAKEOVER,
        Permission.CHATS_TAKEOVER_RELEASE,
        Permission.CONTACTS_DELETE,
        Permission.CONTACTS_MERGE,
        Permission.BOTS_DEACTIVATE_DEPT,
        Permission.AUDIT_READ_DEPARTMENT,
        Permission.ANALYTICS_READ,
        Permission.STATUSES_MANAGE,
    }
)

_SENIOR_DENIED: frozenset[Permission] = ALL_PERMISSIONS - _SENIOR_EXPECTED

_ADMIN_ONLY: frozenset[Permission] = frozenset(
    {
        Permission.USERS_CREATE,
        Permission.USERS_CREATE_SENIOR,
        Permission.USERS_CREATE_ADMIN,
        Permission.USERS_UPDATE_DEPT_TRANSFER,
        Permission.GROUPS_CREATE,
        Permission.DEPARTMENTS_CREATE,
        Permission.DEPARTMENTS_HEAD_ASSIGN,
        Permission.DEPARTMENTS_HEAD_REMOVE,
        Permission.DEPARTMENTS_DELETE,
        Permission.CHATS_READ_ALL,
        Permission.CHATS_READ_GROUP,
        Permission.CHATS_TRANSFER_FORCE,
        Permission.CONTACTS_READ_TG_ID,
        Permission.BOTS_READ_METRICS,
        Permission.BOTS_SECRET_READ,
        Permission.BOTS_MANAGE,
        Permission.BOTS_REASSIGN,
        Permission.BOTS_CONFIG_UPDATE,
        Permission.BOTS_DEACTIVATE,
        Permission.BOTS_SECRET_ROTATE,
        Permission.BOTS_DELETE,
        Permission.AUDIT_READ_ALL,
        Permission.FILES_DELETE,
        Permission.USERS_DELETION_REQUEST_APPROVE,
        Permission.USERS_DELETION_REQUEST_REJECT,
    }
)


@pytest.mark.parametrize(
    ("role", "permission", "expected"),
    [
        *[(UserRole.USER, perm, True) for perm in _USER_EXPECTED],
        *[(UserRole.USER, perm, False) for perm in _USER_DENIED],
        *[(UserRole.SENIOR, perm, True) for perm in _SENIOR_EXPECTED],
        *[(UserRole.SENIOR, perm, False) for perm in _SENIOR_DENIED],
        *[(UserRole.ADMIN, perm, True) for perm in ALL_PERMISSIONS],
    ],
)
def test_role_permission_matrix(role: UserRole, permission: Permission, expected: bool) -> None:
    assert has_permission(role, permission) is expected


def test_role_map_matches_expected_sets() -> None:
    assert ROLE_PERMISSIONS[UserRole.USER] == _USER_EXPECTED
    assert ROLE_PERMISSIONS[UserRole.SENIOR] == _SENIOR_EXPECTED
    assert ROLE_PERMISSIONS[UserRole.ADMIN] == ALL_PERMISSIONS


@pytest.mark.parametrize("permission", list(_ADMIN_ONLY))
def test_admin_only_permissions_denied_for_non_admin(permission: Permission) -> None:
    assert not has_permission(UserRole.USER, permission)
    assert not has_permission(UserRole.SENIOR, permission)
    assert has_permission(UserRole.ADMIN, permission)
