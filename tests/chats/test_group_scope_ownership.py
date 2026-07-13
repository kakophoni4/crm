from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine, text

from app.modules.db.models.enums import UserRole
from app.realtime.events import Event
from app.realtime.scope import WsScope, event_visible
from app.shared.settings import Settings
from tests.auth.conftest import _sync_database_url
from tests.chats.conftest import login


@pytest.mark.asyncio
async def test_user_sees_all_group_chats_not_only_own(
    client: AsyncClient,
    db_ready: None,
    chats_org: dict[str, object],
    operator_a_headers: dict[str, str],
    operator_b_headers: dict[str, str],
) -> None:
    chat_ids = chats_org["chat_ids"]
    assert isinstance(chat_ids, dict)

    for headers in (operator_a_headers, operator_b_headers):
        response = await client.get("/api/v1/chats", headers=headers)
        assert response.status_code == 200
        ids = {item["id"] for item in response.json()["items"]}
        assert chat_ids["a"] in ids
        assert chat_ids["b"] in ids


@pytest.mark.asyncio
async def test_on_behalf_audit_when_colleague_replies(
    client: AsyncClient,
    db_ready: None,
    chats_org: dict[str, object],
    test_settings: Settings,
) -> None:
    user_ids = chats_org["user_ids"]
    assert isinstance(user_ids, dict)
    contact_id = chats_org["contact_ids"]["a"]
    assert isinstance(contact_id, int)

    engine = create_engine(_sync_database_url(test_settings.database_url))
    with engine.begin() as connection:
        group_row = connection.execute(
            text(
                """
                SELECT id FROM groups
                WHERE department_id = :dept_id AND name = 'Chats Group A'
                """
            ),
            {"dept_id": chats_org["dept_a"]},
        ).scalar_one()
        connection.execute(
            text(
                """
                INSERT INTO contact_group_assignments (
                    contact_id, group_id, owner_user_id, assignment_source
                )
                VALUES (:cid, :gid, :owner, 'auto_round_robin')
                ON CONFLICT (contact_id, group_id) DO UPDATE
                SET owner_user_id = EXCLUDED.owner_user_id
                """
            ),
            {
                "cid": contact_id,
                "gid": group_row,
                "owner": user_ids["operator.chats.a@crm.local"],
            },
        )
    engine.dispose()

    password = str(chats_org["password"])
    emails = chats_org["emails"]
    assert isinstance(emails, dict)
    token_b = await login(client, str(emails["operator_b"]), password)
    headers_b = {"Authorization": f"Bearer {token_b}"}
    chat_id = chats_org["chat_ids"]["a"]
    assert isinstance(chat_id, int)

    response = await client.post(
        f"/api/v1/chats/{chat_id}/messages",
        headers=headers_b,
        json={"text": "Reply for colleague", "kind": "text", "idempotency_key": "on-behalf-1"},
    )
    assert response.status_code == 202, response.text
    payload = response.json()
    assert payload["card_owner_user_id"] == user_ids["operator.chats.a@crm.local"]
    assert payload["card_owner_group_id"] == group_row
    assert payload["card_owner_name"] is not None

    engine = create_engine(_sync_database_url(test_settings.database_url))
    with engine.connect() as connection:
        audit = connection.execute(
            text(
                """
                SELECT card_owner_user_id, author_user_id, is_on_behalf
                FROM message_reply_audit
                WHERE chat_id = :chat_id
                ORDER BY id DESC LIMIT 1
                """
            ),
            {"chat_id": chat_id},
        ).one()
    engine.dispose()

    assert audit[2] is True
    assert audit[0] == user_ids["operator.chats.a@crm.local"]
    assert audit[1] == user_ids["operator.chats.b@crm.local"]


@pytest.mark.asyncio
async def test_colleague_can_send_when_not_owner(
    client: AsyncClient,
    db_ready: None,
    chats_org: dict[str, object],
    operator_b_headers: dict[str, str],
) -> None:
    chat_id = chats_org["chat_ids"]["a"]
    assert isinstance(chat_id, int)
    response = await client.post(
        f"/api/v1/chats/{chat_id}/messages",
        headers=operator_b_headers,
        json={"text": "Group member reply", "kind": "text", "idempotency_key": "colleague-send"},
    )
    assert response.status_code == 202, response.text


@pytest.mark.asyncio
async def test_owner_notify_ws_scope(
    db_ready: None,
    ownership_org: dict[str, object],
) -> None:
    user_ids = ownership_org["user_ids"]
    assert isinstance(user_ids, dict)
    owner_id = user_ids["owner.op1@crm.local"]
    other_id = user_ids["owner.op2@crm.local"]
    group_id = int(ownership_org["group_id"])

    event = Event(
        topic="contact.escalation.owner_notify",
        payload={"owner_user_id": owner_id},
        scope={"user_id": owner_id},
    )
    owner_scope = WsScope(
        user_id=owner_id,
        role=UserRole.USER,
        department_id=int(ownership_org["dept_id"]),
        group_id=group_id,
        actor_group_ids=frozenset({group_id}),
        department_group_ids=frozenset(),
        visible_user_ids=frozenset({owner_id}),
    )
    other_scope = WsScope(
        user_id=other_id,
        role=UserRole.USER,
        department_id=int(ownership_org["dept_id"]),
        group_id=group_id,
        actor_group_ids=frozenset({group_id}),
        department_group_ids=frozenset(),
        visible_user_ids=frozenset({other_id}),
    )
    assert event_visible(owner_scope, event) is True
    assert event_visible(other_scope, event) is False


@pytest.mark.asyncio
async def test_group_notify_visible_to_group_members(
    db_ready: None,
    ownership_org: dict[str, object],
) -> None:
    user_ids = ownership_org["user_ids"]
    assert isinstance(user_ids, dict)
    group_id = int(ownership_org["group_id"])
    event = Event(
        topic="contact.escalation.group_notify",
        payload={"group_id": group_id},
        scope={"group_id": group_id},
    )
    member_scope = WsScope(
        user_id=user_ids["owner.op1@crm.local"],
        role=UserRole.USER,
        department_id=int(ownership_org["dept_id"]),
        group_id=group_id,
        actor_group_ids=frozenset({group_id}),
        department_group_ids=frozenset(),
        visible_user_ids=frozenset(),
    )
    assert event_visible(member_scope, event) is True


@pytest.mark.asyncio
async def test_inbound_message_visible_to_group_members(
    db_ready: None,
    ownership_org: dict[str, object],
) -> None:
    user_ids = ownership_org["user_ids"]
    assert isinstance(user_ids, dict)
    group_id = int(ownership_org["group_id"])
    event = Event(
        topic="chat.message.inbound",
        payload={"chat_id": 1, "message_id": 99},
        scope={"group_id": group_id},
    )
    member_scope = WsScope(
        user_id=user_ids["owner.op1@crm.local"],
        role=UserRole.USER,
        department_id=int(ownership_org["dept_id"]),
        group_id=None,
        actor_group_ids=frozenset({group_id}),
        department_group_ids=frozenset(),
        visible_user_ids=frozenset(),
    )
    outsider_scope = WsScope(
        user_id=user_ids["owner.op2@crm.local"],
        role=UserRole.USER,
        department_id=int(ownership_org["dept_id"]),
        group_id=None,
        actor_group_ids=frozenset(),
        department_group_ids=frozenset(),
        visible_user_ids=frozenset(),
    )
    assert event_visible(member_scope, event) is True
    assert event_visible(outsider_scope, event) is False


@pytest.mark.asyncio
async def test_inbound_message_visible_with_department_and_group_scope(
    db_ready: None,
    ownership_org: dict[str, object],
) -> None:
    """Regression: department_id must not hide group-scoped chat events from operators."""
    user_ids = ownership_org["user_ids"]
    assert isinstance(user_ids, dict)
    group_id = int(ownership_org["group_id"])
    dept_id = int(ownership_org["dept_id"])
    event = Event(
        topic="chat.message.inbound",
        payload={"chat_id": 1, "message_id": 99},
        scope={"department_id": dept_id, "group_id": group_id},
    )
    member_scope = WsScope(
        user_id=user_ids["owner.op1@crm.local"],
        role=UserRole.USER,
        department_id=dept_id,
        group_id=None,
        actor_group_ids=frozenset({group_id}),
        department_group_ids=frozenset(),
        visible_user_ids=frozenset(),
    )
    outsider_scope = WsScope(
        user_id=user_ids["owner.op2@crm.local"],
        role=UserRole.USER,
        department_id=dept_id,
        group_id=None,
        actor_group_ids=frozenset(),
        department_group_ids=frozenset(),
        visible_user_ids=frozenset(),
    )
    assert event_visible(member_scope, event) is True
    assert event_visible(outsider_scope, event) is False


@pytest.mark.asyncio
async def test_inbound_message_without_scope_hidden_from_users(
    db_ready: None,
    ownership_org: dict[str, object],
) -> None:
    user_ids = ownership_org["user_ids"]
    assert isinstance(user_ids, dict)
    event = Event(
        topic="chat.message.inbound",
        payload={"chat_id": 1, "message_id": 99},
        scope={},
    )
    member_scope = WsScope(
        user_id=user_ids["owner.op1@crm.local"],
        role=UserRole.USER,
        department_id=int(ownership_org["dept_id"]),
        group_id=int(ownership_org["group_id"]),
        actor_group_ids=frozenset({int(ownership_org["group_id"])}),
        department_group_ids=frozenset(),
        visible_user_ids=frozenset(),
    )
    assert event_visible(member_scope, event) is False
