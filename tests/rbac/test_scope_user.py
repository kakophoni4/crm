from __future__ import annotations

import pytest

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


@pytest.fixture
def operator() -> ScopeContext:
    actor = make_user(user_id=10, role=UserRole.USER, department_id=1, group_id=100)
    return ScopeContext(
        actor=actor,
        actor_group_ids=frozenset({100}),
        group_member_ids=frozenset({10, 11, 12}),
        department_senior_id=50,
        department_user_ids=frozenset({10, 11, 12, 20, 50}),
        department_group_ids=frozenset({100, 101}),
    )


def test_visible_group_ids_multiple_groups() -> None:
    actor = make_user(user_id=10, role=UserRole.USER, department_id=1, group_id=None)
    ctx = ScopeContext(actor=actor, actor_group_ids=frozenset({100, 101}))
    assert visible_group_ids(ctx) == {100, 101}


def test_visible_user_ids_includes_self_group_and_senior(operator: ScopeContext) -> None:
    result = visible_user_ids(operator)
    assert result == {10, 11, 12, 50}


def test_visible_group_ids_own_group_only(operator: ScopeContext) -> None:
    assert visible_group_ids(operator) == {100}


def test_visible_department_ids_own_department_only(operator: ScopeContext) -> None:
    assert visible_department_ids(operator) == {1}


@pytest.mark.parametrize(
    ("target_id", "target_group", "expected"),
    [
        (10, 100, True),
        (11, 100, True),
        (50, None, True),
        (20, 101, False),
        (99, 200, False),
    ],
)
def test_can_act_on_user_group_and_senior_rules(
    operator: ScopeContext,
    target_id: int,
    target_group: int | None,
    expected: bool,
) -> None:
    target = make_user(
        user_id=target_id,
        role=UserRole.USER,
        department_id=1,
        group_id=target_group,
    )
    assert can_act_on_user(operator, target) is expected


def test_user_without_group_sees_only_self_and_senior() -> None:
    actor = make_user(user_id=1, role=UserRole.USER, department_id=5, group_id=None)
    ctx = ScopeContext(actor=actor, department_senior_id=99)
    assert visible_user_ids(ctx) == {1, 99}
    assert visible_group_ids(ctx) == set()


def test_user_never_gets_scope_all() -> None:
    actor = make_user(user_id=1, role=UserRole.USER, department_id=1, group_id=1)
    ctx = ScopeContext(actor=actor)
    assert visible_user_ids(ctx) != SCOPE_ALL
    assert visible_group_ids(ctx) != SCOPE_ALL
    assert visible_department_ids(ctx) != SCOPE_ALL
