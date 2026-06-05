from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine, text

from app.shared.settings import Settings
from tests.auth.conftest import _sync_database_url
from tests.chats.conftest import login

MATRIX: list[tuple[str, str, str | None, int]] = [
    ("GET", "/api/v1/chats", None, 401),
    ("GET", "/api/v1/contacts", None, 401),
    ("GET", "/api/v1/contacts/1/leads", None, 401),
    ("GET", "/api/v1/leads/1", None, 401),
    ("GET", "/api/v1/auth/me", None, 401),
    ("POST", "/api/v1/auth/login", None, 422),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("method", "path", "token", "expected"), MATRIX)
async def test_endpoint_auth_matrix(
    client: AsyncClient,
    method: str,
    path: str,
    token: str | None,
    expected: int,
    db_ready: None,
) -> None:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    response = await client.request(method, path, headers=headers)
    assert response.status_code == expected


@pytest.mark.asyncio
async def test_operator_can_list_chats(
    client: AsyncClient,
    chats_org: dict[str, object],
    db_ready: None,
) -> None:
    emails = chats_org["emails"]
    assert isinstance(emails, dict)
    token = await login(client, str(emails["operator_a"]), str(chats_org["password"]))
    response = await client.get(
        "/api/v1/chats",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_operator_post_bots_returns_403(
    client: AsyncClient,
    chats_org: dict[str, object],
    operator_a_headers: dict[str, str],
    db_ready: None,
) -> None:
    dept_id = chats_org["dept_a"]
    response = await client.post(
        "/api/v1/bots",
        headers=operator_a_headers,
        json={
            "code": f"rbac_denied_{uuid.uuid4().hex[:8]}",
            "name": "RBAC Denied Bot",
            "owner_type": "department",
            "owner_id": dept_id,
            "outbound_url": "https://example.com/outbound",
            "inbound_secret": "x" * 32,
            "outbound_secret": "y" * 32,
        },
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_operator_patch_bot_returns_403(
    client: AsyncClient,
    admin_headers: dict[str, str],
    operator_a_headers: dict[str, str],
    chats_org: dict[str, object],
    db_ready: None,
) -> None:
    dept_id = chats_org["dept_a"]
    created = await client.post(
        "/api/v1/bots",
        headers=admin_headers,
        json={
            "code": f"rbac_patch_{uuid.uuid4().hex[:8]}",
            "name": "RBAC Patch Bot",
            "owner_type": "department",
            "owner_id": dept_id,
            "outbound_url": "https://example.com/outbound",
            "inbound_secret": "a" * 32,
            "outbound_secret": "b" * 32,
        },
    )
    assert created.status_code == 201, created.text
    bot_id = created.json()["id"]

    response = await client.patch(
        f"/api/v1/bots/{bot_id}",
        headers=operator_a_headers,
        json={"name": "Hijacked"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_operator_post_status_returns_403(
    client: AsyncClient,
    operator_a_headers: dict[str, str],
    db_ready: None,
) -> None:
    response = await client.post(
        "/api/v1/statuses",
        headers=operator_a_headers,
        json={"code": "rbac_forbidden", "label": "RBAC Forbidden", "color": "#ff0000"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_user_cannot_get_other_group_chat_by_id(
    client: AsyncClient,
    rbac_cross_group_org: dict[str, object],
    rbac_xg_op_b_headers: dict[str, str],
    db_ready: None,
) -> None:
    chat_ids = rbac_cross_group_org["chat_ids"]
    assert isinstance(chat_ids, dict)
    foreign_chat_id = chat_ids["a"]

    response = await client.get(
        f"/api/v1/chats/{foreign_chat_id}",
        headers=rbac_xg_op_b_headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_user_cannot_list_messages_on_other_group_chat(
    client: AsyncClient,
    rbac_cross_group_org: dict[str, object],
    rbac_xg_op_b_headers: dict[str, str],
    db_ready: None,
) -> None:
    chat_ids = rbac_cross_group_org["chat_ids"]
    assert isinstance(chat_ids, dict)

    response = await client.get(
        f"/api/v1/chats/{chat_ids['a']}/messages",
        headers=rbac_xg_op_b_headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_user_cannot_post_message_to_other_group_chat(
    client: AsyncClient,
    rbac_cross_group_org: dict[str, object],
    rbac_xg_op_b_headers: dict[str, str],
    db_ready: None,
) -> None:
    chat_ids = rbac_cross_group_org["chat_ids"]
    assert isinstance(chat_ids, dict)

    response = await client.post(
        f"/api/v1/chats/{chat_ids['a']}/messages",
        headers=rbac_xg_op_b_headers,
        json={"body": "IDOR probe", "client_message_id": f"rbac-idor-{uuid.uuid4().hex}"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_user_cannot_mark_read_other_group_chat(
    client: AsyncClient,
    rbac_cross_group_org: dict[str, object],
    rbac_xg_op_b_headers: dict[str, str],
    db_ready: None,
) -> None:
    chat_ids = rbac_cross_group_org["chat_ids"]
    assert isinstance(chat_ids, dict)

    response = await client.post(
        f"/api/v1/chats/{chat_ids['a']}/read",
        headers=rbac_xg_op_b_headers,
        json={},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_user_cannot_get_lead_in_other_group(
    client: AsyncClient,
    rbac_cross_group_org: dict[str, object],
    rbac_xg_op_b_headers: dict[str, str],
    test_settings: Settings,
    db_ready: None,
) -> None:
    contact_ids = rbac_cross_group_org["contact_ids"]
    group_a = rbac_cross_group_org["group_a"]
    chat_ids = rbac_cross_group_org["chat_ids"]
    assert isinstance(contact_ids, dict)
    assert isinstance(chat_ids, dict)

    engine = create_engine(_sync_database_url(test_settings.database_url))
    try:
        with engine.begin() as conn:
            status_id = conn.execute(
                text(
                    """
                    SELECT id FROM statuses
                    WHERE code = 'new' AND kind = 'lead_pipeline'
                    LIMIT 1
                    """
                ),
            ).scalar_one()
            lead_id = conn.execute(
                text(
                    """
                    INSERT INTO leads (contact_id, group_id, chat_id, status_id, title)
                    VALUES (:cid, :gid, :chat_id, :status_id, 'RBAC foreign lead')
                    RETURNING id
                    """
                ),
                {
                    "cid": contact_ids["a"],
                    "gid": group_a,
                    "chat_id": chat_ids["a"],
                    "status_id": status_id,
                },
            ).scalar_one()
    finally:
        engine.dispose()

    response = await client.get(
        f"/api/v1/leads/{lead_id}",
        headers=rbac_xg_op_b_headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_user_cannot_post_lead_in_foreign_group(
    client: AsyncClient,
    leads_api_org: dict[str, object],
    db_ready: None,
) -> None:
    emails = leads_api_org["emails"]
    assert isinstance(emails, dict)
    token = await login(client, str(emails["op_b"]), str(leads_api_org["password"]))

    response = await client.post(
        f"/api/v1/contacts/{leads_api_org['contact_id']}/leads",
        headers={"Authorization": f"Bearer {token}"},
        json={"group_id": leads_api_org["group_a"]},
    )
    assert response.status_code in {403, 404}, response.text


@pytest.mark.asyncio
async def test_user_list_contact_leads_excludes_foreign_group(
    client: AsyncClient,
    leads_api_org: dict[str, object],
    db_ready: None,
) -> None:
    emails = leads_api_org["emails"]
    assert isinstance(emails, dict)
    token = await login(client, str(emails["op_b"]), str(leads_api_org["password"]))

    response = await client.get(
        f"/api/v1/contacts/{leads_api_org['contact_id']}/leads",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    group_ids = {item["group_id"] for item in response.json()["items"]}
    assert leads_api_org["group_a"] not in group_ids
    assert group_ids <= {leads_api_org["group_b"]}


@pytest.mark.asyncio
async def test_contact_other_department_returns_404(
    client: AsyncClient,
    chats_org: dict[str, object],
    operator_a_headers: dict[str, str],
    db_ready: None,
) -> None:
    contact_ids = chats_org["contact_ids"]
    assert isinstance(contact_ids, dict)

    response = await client.get(
        f"/api/v1/contacts/{contact_ids['dept_b']}",
        headers=operator_a_headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_contact_audit_other_department_returns_404(
    client: AsyncClient,
    chats_org: dict[str, object],
    operator_a_headers: dict[str, str],
    db_ready: None,
) -> None:
    contact_ids = chats_org["contact_ids"]
    assert isinstance(contact_ids, dict)

    response = await client.get(
        f"/api/v1/contacts/{contact_ids['dept_b']}/audit",
        headers=operator_a_headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_chat_other_department_by_id_returns_404(
    client: AsyncClient,
    chats_org: dict[str, object],
    operator_a_headers: dict[str, str],
    db_ready: None,
) -> None:
    chat_ids = chats_org["chat_ids"]
    assert isinstance(chat_ids, dict)

    response = await client.get(
        f"/api/v1/chats/{chat_ids['dept_b']}",
        headers=operator_a_headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_search_messages_does_not_leak_other_department(
    client: AsyncClient,
    chats_org: dict[str, object],
    operator_a_headers: dict[str, str],
    test_settings: Settings,
    db_ready: None,
) -> None:
    chat_id = chats_org["chat_ids"]["dept_b"]
    assert isinstance(chat_id, int)
    secret_word = "rbacsearchleak99"

    engine = create_engine(_sync_database_url(test_settings.database_url))
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO messages (chat_id, direction, kind, text)
                VALUES (:chat_id, 'inbound', 'text', :body)
                """
            ),
            {"chat_id": chat_id, "body": f"Секрет {secret_word} вне скоупа"},
        )
    engine.dispose()

    response = await client.get(
        "/api/v1/search",
        headers=operator_a_headers,
        params={"q": secret_word, "types": "messages"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["messages"]["items"] == []


@pytest.mark.asyncio
async def test_search_contacts_does_not_leak_other_department(
    client: AsyncClient,
    chats_org: dict[str, object],
    operator_a_headers: dict[str, str],
    db_ready: None,
) -> None:
    response = await client.get(
        "/api/v1/search",
        headers=operator_a_headers,
        params={"q": "Chat Contact DeptB", "types": "contacts"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["contacts"]["items"] == []


@pytest.mark.asyncio
async def test_search_chats_does_not_leak_other_department(
    client: AsyncClient,
    chats_org: dict[str, object],
    operator_a_headers: dict[str, str],
    db_ready: None,
) -> None:
    response = await client.get(
        "/api/v1/search",
        headers=operator_a_headers,
        params={"q": "Preview dept_b", "types": "chats"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["chats"]["items"] == []


@pytest.mark.asyncio
async def test_operator_cannot_patch_contact_in_other_department(
    client: AsyncClient,
    chats_org: dict[str, object],
    operator_a_headers: dict[str, str],
    db_ready: None,
) -> None:
    contact_ids = chats_org["contact_ids"]
    assert isinstance(contact_ids, dict)

    response = await client.patch(
        f"/api/v1/contacts/{contact_ids['dept_b']}",
        headers=operator_a_headers,
        json={"full_name": "IDOR rename attempt"},
    )
    assert response.status_code == 404
