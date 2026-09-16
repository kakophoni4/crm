from app.modules.db.models.enums import UserRole
from app.modules.rbac.permissions import Permission
from app.modules.rbac.role_map import ROLE_PERMISSIONS, has_permission


def test_nulevka_has_storage_but_no_business_or_admin_permissions():
    permissions = ROLE_PERMISSIONS[UserRole.NULEVKA]
    assert {Permission.FILES_DOWNLOAD, Permission.FILES_UPLOAD, Permission.FILES_DELETE} <= permissions
    assert all(p.value.startswith(("files.", "profile.")) for p in permissions)
    assert not has_permission(UserRole.NULEVKA, Permission.CASHROOM_MANAGE)
    assert not has_permission(UserRole.NULEVKA, Permission.USERS_CREATE)
    assert not has_permission(UserRole.NULEVKA, Permission.TASKS_READ)


def test_kesher_keeps_cashroom_and_gains_storage():
    for permission in (Permission.CASHROOM_MANAGE, Permission.FILES_DOWNLOAD,
                       Permission.FILES_UPLOAD, Permission.FILES_DELETE):
        assert has_permission(UserRole.KESHER, permission)
    assert not has_permission(UserRole.KESHER, Permission.USERS_CREATE)


def test_every_role_has_a_permission_mapping():
    assert set(ROLE_PERMISSIONS) == set(UserRole)
