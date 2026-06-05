from __future__ import annotations

import pytest

from app.modules.db.models.enums import UserRole
from app.modules.db.models.user import User
from app.modules.rbac.scope import (
    ScopeContext,
    can_act_on_user,
    visible_department_ids,
    visible_group_ids,
    visible_user_ids,
)
from tests.rbac.conftest import make_user


@pytest.fixture
def senior_ctx() -> ScopeContext:
    actor = make_user(user_id=50, role=UserRole.SENIOR, department_id=1, group_id=None)
    return ScopeContext(
        actor=actor,
        department_user_ids=frozenset({10, 11, 20, 50}),
        department_group_ids=frozenset({100, 101}),
        department_senior_id=50,
    )


def test_visible_user_ids_entire_department(senior_ctx: ScopeContext) -> None:
    assert visible_user_ids(senior_ctx) == {10, 11, 20, 50}


def test_visible_group_ids_entire_department(senior_ctx: ScopeContext) -> None:
    assert visible_group_ids(senior_ctx) == {100, 101}


def test_visible_department_ids_own_department(senior_ctx: ScopeContext) -> None:
    assert visible_department_ids(senior_ctx) == {1}


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        (make_user(user_id=10, role=UserRole.USER, department_id=1, group_id=100), True),
        (make_user(user_id=60, role=UserRole.SENIOR, department_id=1, group_id=None), False),
        (make_user(user_id=70, role=UserRole.USER, department_id=2, group_id=200), False),
    ],
)
def test_can_act_on_user_department_excludes_other_seniors(
    senior_ctx: ScopeContext,
    target: User,
    expected: bool,
) -> None:
    assert can_act_on_user(senior_ctx, target) is expected


def test_senior_without_department_falls_back_to_self() -> None:
    actor = make_user(user_id=50, role=UserRole.SENIOR, department_id=None, group_id=None)
    ctx = ScopeContext(actor=actor, department_user_ids=frozenset({10}))
    assert visible_user_ids(ctx) == {50}
    assert visible_group_ids(ctx) == set()
    assert visible_department_ids(ctx) == set()
