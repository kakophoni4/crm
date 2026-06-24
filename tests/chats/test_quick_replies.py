from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_group_quick_reply_visible_across_group_and_hide_is_per_user(
    client: AsyncClient,
    db_ready: None,
    chats_org: dict[str, object],
    operator_a_headers: dict[str, str],
    operator_b_headers: dict[str, str],
) -> None:
    group_id = int(chats_org["group_a"])
    dept_id = int(chats_org["dept_a"])

    created = await client.post(
        "/api/v1/chats/quick-replies",
        headers=operator_a_headers,
        json={
            "title": "Delivery info",
            "body": "Delivery takes 2 days",
            "department_id": dept_id,
            "group_id": group_id,
            "is_active": True,
        },
    )
    assert created.status_code == 201, created.text
    template_id = int(created.json()["id"])

    operator_b_list = await client.get(
        "/api/v1/chats/quick-replies",
        headers=operator_b_headers,
        params={"group_id": group_id, "q": "Delivery"},
    )
    assert operator_b_list.status_code == 200, operator_b_list.text
    assert any(item["id"] == template_id for item in operator_b_list.json()["items"])

    hidden = await client.post(
        f"/api/v1/chats/quick-replies/{template_id}/hide",
        headers=operator_a_headers,
    )
    assert hidden.status_code == 200, hidden.text

    operator_a_after_hide = await client.get(
        "/api/v1/chats/quick-replies",
        headers=operator_a_headers,
        params={"group_id": group_id, "q": "Delivery"},
    )
    assert operator_a_after_hide.status_code == 200, operator_a_after_hide.text
    assert all(item["id"] != template_id for item in operator_a_after_hide.json()["items"])

    operator_b_after_hide = await client.get(
        "/api/v1/chats/quick-replies",
        headers=operator_b_headers,
        params={"group_id": group_id, "q": "Delivery"},
    )
    assert operator_b_after_hide.status_code == 200, operator_b_after_hide.text
    assert any(item["id"] == template_id for item in operator_b_after_hide.json()["items"])
