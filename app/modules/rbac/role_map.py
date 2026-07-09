from __future__ import annotations

from app.modules.db.models.enums import UserRole
from app.modules.rbac.permissions import ALL_PERMISSIONS, Permission

_USER_PERMISSIONS: frozenset[Permission] = frozenset(
    {
        # §3.1 Auth & profile
        Permission.PROFILE_PASSWORD_UPDATE,
        Permission.PROFILE_FULL_NAME_UPDATE,
        Permission.PROFILE_PRESENCE_UPDATE,
        Permission.PROFILE_AVAILABILITY_UPDATE,
        # §3.2 Users (read scoped)
        Permission.USERS_READ,
        Permission.USERS_READ_GROUP,
        # §3.3 Groups
        Permission.GROUPS_READ,
        Permission.GROUPS_READ_OWN,
        # §3.4 Departments
        Permission.DEPARTMENTS_READ,
        # §3.5 Chats
        Permission.CHATS_READ_OWN,
        Permission.CHATS_WRITE,
        Permission.CHATS_STATUS_UPDATE,
        Permission.CHATS_TRANSFER_REQUEST,
        Permission.CHATS_TRANSFER_CANCEL,
        Permission.CHATS_ARCHIVE,
        # §3.6 Contacts
        Permission.CONTACTS_READ,
        Permission.CONTACTS_READ_TELEGRAM_USERNAME,
        Permission.CONTACTS_CREATE,
        Permission.CONTACTS_UPDATE,
        Permission.CONTACTS_AUDIT_READ,
        # §3.7 Bots
        Permission.BOTS_READ,
        Permission.TELEPHONY_READ,
        Permission.TELEPHONY_CALL,
        # §3.8 Statuses
        Permission.STATUSES_READ,
        # §3.9 Audit
        Permission.AUDIT_READ_OWN,
        # §3.10 Files
        Permission.FILES_UPLOAD,
        Permission.FILES_DOWNLOAD,
        Permission.FILES_DELETE,
        # Tasks
        Permission.TASKS_READ,
    }
)

_SENIOR_EXTRA: frozenset[Permission] = frozenset(
    {
        # §3.2 Users
        Permission.USERS_CREATE_IN_DEP,
        Permission.USERS_UPDATE,
        Permission.USERS_UPDATE_GROUP_TRANSFER,
        Permission.USERS_PASSWORD_RESET,
        Permission.USERS_FORCE_LOGOUT,
        Permission.USERS_DEACTIVATE,
        Permission.USERS_DELETION_REQUEST_CREATE,
        Permission.USERS_DELETION_REQUEST_READ,
        # §3.3 Groups
        Permission.GROUPS_CREATE_IN_DEP,
        Permission.GROUPS_UPDATE,
        Permission.GROUPS_DELETE,
        # §3.5 Chats
        Permission.CHATS_READ_DEPARTMENT,
        Permission.CHATS_TRANSFER_APPROVE,
        Permission.CHATS_TAKEOVER,
        Permission.CHATS_TAKEOVER_RELEASE,
        # §3.6 Contacts
        Permission.CONTACTS_DELETE,
        Permission.CONTACTS_MERGE,
        # §3.7 Bots
        Permission.BOTS_DEACTIVATE_DEPT,
        Permission.BOTS_REASSIGN,
        Permission.TELEPHONY_MANAGE,
        # §3.9 Audit
        Permission.AUDIT_READ_DEPARTMENT,
        # Analytics
        Permission.ANALYTICS_READ,
        # §3.8 Statuses (воронка сделок в отделе)
        Permission.STATUSES_MANAGE,
        # Tasks
        Permission.TASKS_MANAGE,
    }
)

_SENIOR_PERMISSIONS: frozenset[Permission] = (
    _USER_PERMISSIONS - {Permission.CHATS_READ_OWN}
) | _SENIOR_EXTRA

_ADMIN_PERMISSIONS: frozenset[Permission] = ALL_PERMISSIONS

_ACCOUNTANT_PERMISSIONS: frozenset[Permission] = frozenset(
    {
        Permission.PROFILE_PASSWORD_UPDATE,
        Permission.PROFILE_FULL_NAME_UPDATE,
        Permission.PROFILE_PRESENCE_UPDATE,
        Permission.PROFILE_AVAILABILITY_UPDATE,
        Permission.FILES_DOWNLOAD,
        Permission.ACCOUNTING_READ,
        Permission.ACCOUNTING_MANAGE,
    }
)

ROLE_PERMISSIONS: dict[UserRole, frozenset[Permission]] = {
    UserRole.USER: _USER_PERMISSIONS,
    UserRole.SENIOR: _SENIOR_PERMISSIONS,
    UserRole.ADMIN: _ADMIN_PERMISSIONS,
    UserRole.ACCOUNTANT: _ACCOUNTANT_PERMISSIONS,
}


def has_permission(role: UserRole, perm: Permission) -> bool:
    if role == UserRole.ADMIN:
        return True
    return perm in ROLE_PERMISSIONS[role]


def has_any_permission(role: UserRole, perms: tuple[Permission, ...]) -> bool:
    return any(has_permission(role, perm) for perm in perms)


def has_all_permissions(role: UserRole, perms: tuple[Permission, ...]) -> bool:
    return all(has_permission(role, perm) for perm in perms)
