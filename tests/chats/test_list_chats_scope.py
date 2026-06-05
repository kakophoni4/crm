from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_chats_scope_user_senior_admin(
    client: AsyncClient,
    db_ready: None,
    chats_org: dict[str, object],
    operator_a_headers: dict[str, str],
    operator_b_headers: dict[str, str],
    senior_headers: dict[str, str],
    admin_headers: dict[str, str],
) -> None:
    chat_ids = chats_org["chat_ids"]
    assert isinstance(chat_ids, dict)

    resp_a = await client.get("/api/v1/chats", headers=operator_a_headers)
    assert resp_a.status_code == 200
    first_item = resp_a.json()["items"][0]
    assert "card_owner_user_id" in first_item
    assert "card_owner_name" in first_item
    assert "card_owner_group_id" in first_item
    ids_a = {item["id"] for item in resp_a.json()["items"]}
    assert chat_ids["a"] in ids_a
    assert chat_ids["b"] in ids_a

    resp_b = await client.get("/api/v1/chats", headers=operator_b_headers)
    ids_b = {item["id"] for item in resp_b.json()["items"]}
    assert chat_ids["b"] in ids_b
    assert chat_ids["a"] in ids_b

    resp_senior = await client.get("/api/v1/chats", headers=senior_headers)
    ids_senior = {item["id"] for item in resp_senior.json()["items"]}
    assert chat_ids["a"] in ids_senior
    assert chat_ids["b"] in ids_senior
    assert chat_ids["dept_b"] not in ids_senior

    resp_admin = await client.get("/api/v1/chats", headers=admin_headers)
    ids_admin = {item["id"] for item in resp_admin.json()["items"]}
    assert chat_ids["dept_b"] in ids_admin
