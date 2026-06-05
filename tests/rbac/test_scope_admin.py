from __future__ import annotations

from app.modules.db.models.enums import UserRole
from app.modules.rbac.scope import (
    SCOPE_ALL,
    ScopeContext,
    can_act_on_user,
    visible_department_ids,
    visible_group_ids,
    visible_user_ids,
)
from tests.rbac.conftest import make_user


def test_admin_visible_scopes_are_all() -> None:
    admin = make_user(user_id=1, role=UserRole.ADMIN, department_id=None, group_id=None)
    ctx = ScopeContext(actor=admin)
    assert visible_user_ids(ctx) == SCOPE_ALL
    assert visible_group_ids(ctx) == SCOPE_ALL
    assert visible_department_ids(ctx) == SCOPE_ALL


def test_admin_can_act_on_any_user() -> None:
    admin = make_user(user_id=1, role=UserRole.ADMIN)
    ctx = ScopeContext(actor=admin)
    target = make_user(user_id=999, role=UserRole.SENIOR, department_id=5, group_id=None)
    assert can_act_on_user(ctx, target) is True
