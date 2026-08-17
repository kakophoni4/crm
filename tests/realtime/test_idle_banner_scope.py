from __future__ import annotations

from app.modules.db.models.enums import UserRole
from app.realtime.events import Event
from app.realtime.scope import WsScope, event_visible
from app.realtime.topics import IDLE_BANNER_SETTINGS, IDLE_BANNER_SHOW


def _scope(user_id: int, role: UserRole = UserRole.USER) -> WsScope:
    return WsScope(
        user_id=user_id,
        role=role,
        department_id=1,
        group_id=1,
        actor_group_ids=frozenset({1}),
        department_group_ids=frozenset({1}),
        visible_user_ids=frozenset({user_id}),
    )


def test_idle_banner_show_only_target_user() -> None:
    event = Event(topic=IDLE_BANNER_SHOW, payload={"user_id": 5}, scope={"user_id": 5})
    assert event_visible(_scope(5), event) is True
    assert event_visible(_scope(9), event) is False
    assert event_visible(_scope(1, UserRole.ADMIN), event) is False


def test_idle_banner_settings_broadcast() -> None:
    event = Event(topic=IDLE_BANNER_SETTINGS, payload={"is_enabled": True}, scope={})
    assert event_visible(_scope(5), event) is True
    assert event_visible(_scope(1, UserRole.ADMIN), event) is True
