from __future__ import annotations

from enum import StrEnum


class Permission(StrEnum):
    """Permission slugs — must match docs/RBAC_MATRIX.md."""

    # Profile (self-service)
    PROFILE_PASSWORD_UPDATE = "profile.password.update"
    PROFILE_FULL_NAME_UPDATE = "profile.full_name.update"
    PROFILE_PRESENCE_UPDATE = "profile.presence.update"
    PROFILE_AVAILABILITY_UPDATE = "profile.availability.update"

    # Users
    USERS_READ = "users.read"
    USERS_READ_GROUP = "users.read.group"
    USERS_CREATE = "users.create"
    USERS_CREATE_IN_DEP = "users.create.in_dep"
    USERS_CREATE_SENIOR = "users.create.senior"
    USERS_CREATE_ADMIN = "users.create.admin"
    USERS_UPDATE = "users.update"
    USERS_UPDATE_GROUP_TRANSFER = "users.update.group_transfer"
    USERS_UPDATE_DEPT_TRANSFER = "users.update.dept_transfer"
    USERS_DEACTIVATE = "users.deactivate"
    USERS_PASSWORD_RESET = "users.password.reset"
    USERS_FORCE_LOGOUT = "users.force_logout"
    USERS_DELETION_REQUEST_CREATE = "users.deletion_request.create"
    USERS_DELETION_REQUEST_READ = "users.deletion_request.read"
    USERS_DELETION_REQUEST_APPROVE = "users.deletion_request.approve"
    USERS_DELETION_REQUEST_REJECT = "users.deletion_request.reject"

    # Groups
    GROUPS_READ = "groups.read"
    GROUPS_READ_OWN = "groups.read.own"
    GROUPS_CREATE = "groups.create"
    GROUPS_CREATE_IN_DEP = "groups.create.in_dep"
    GROUPS_UPDATE = "groups.update"
    GROUPS_DELETE = "groups.delete"

    # Departments
    DEPARTMENTS_READ = "departments.read"
    DEPARTMENTS_CREATE = "departments.create"
    DEPARTMENTS_HEAD_ASSIGN = "departments.head.assign"
    DEPARTMENTS_HEAD_REMOVE = "departments.head.remove"
    DEPARTMENTS_DELETE = "departments.delete"

    # Chats
    CHATS_READ_OWN = "chats.read.own"
    CHATS_READ_GROUP = "chats.read.group"
    CHATS_READ_DEPARTMENT = "chats.read.department"
    CHATS_READ_ALL = "chats.read.all"
    CHATS_WRITE = "chats.write"
    CHATS_STATUS_UPDATE = "chats.status.update"
    CHATS_TRANSFER_REQUEST = "chats.transfer.request"
    CHATS_TRANSFER_APPROVE = "chats.transfer.approve"
    CHATS_TRANSFER_FORCE = "chats.transfer.force"
    CHATS_TRANSFER_CANCEL = "chats.transfer.cancel"
    CHATS_TAKEOVER = "chats.takeover"
    CHATS_TAKEOVER_RELEASE = "chats.takeover.release"
    CHATS_ARCHIVE = "chats.archive"

    # Contacts
    CONTACTS_READ = "contacts.read"
    CONTACTS_READ_TELEGRAM_USERNAME = "contacts.read.telegram_username"
    CONTACTS_READ_TG_ID = "contacts.read_tg_id"
    CONTACTS_CREATE = "contacts.create"
    CONTACTS_UPDATE = "contacts.update"
    CONTACTS_AUDIT_READ = "contacts.audit.read"
    CONTACTS_DELETE = "contacts.delete"
    CONTACTS_MERGE = "contacts.merge"

    # Bots
    BOTS_READ = "bots.read"
    BOTS_READ_METRICS = "bots.read.metrics"
    BOTS_SECRET_READ = "bots.secret.read"
    BOTS_MANAGE = "bots.manage"
    BOTS_REASSIGN = "bots.reassign"
    BOTS_CONFIG_UPDATE = "bots.config.update"
    BOTS_DEACTIVATE = "bots.deactivate"
    BOTS_DEACTIVATE_DEPT = "bots.deactivate.dept"
    BOTS_SECRET_ROTATE = "bots.secret.rotate"
    BOTS_DELETE = "bots.delete"

    # Statuses
    STATUSES_READ = "statuses.read"
    STATUSES_MANAGE = "statuses.manage"

    # Audit
    AUDIT_READ_OWN = "audit.read.own"
    AUDIT_READ_DEPARTMENT = "audit.read.department"
    AUDIT_READ_ALL = "audit.read.all"

    # Analytics
    ANALYTICS_READ = "analytics.read"

    # Files
    FILES_UPLOAD = "files.upload"
    FILES_DOWNLOAD = "files.download"
    FILES_DELETE = "files.delete"


ALL_PERMISSIONS: frozenset[Permission] = frozenset(Permission)
