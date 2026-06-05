from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.shared.settings import Settings
from tests.contacts.test_contact_transfer_full_flow import _ensure_owner


@pytest.mark.asyncio
async def test_approve_transfer_wrong_version_returns_409(
    client: AsyncClient,
    ownership_org: dict[str, object],
    ownership_op1_headers: dict[str, str],
    ownership_senior_headers: dict[str, str],
    test_settings: Settings,
    db_ready: None,
) -> None:
    group_id = int(ownership_org["group_id"])
    contact_id = int(ownership_org["contact_ids"][0])
    user_ids = ownership_org["user_ids"]
    assert isinstance(user_ids, dict)
    op1_id = user_ids["owner.op1@crm.local"]
    op2_id = user_ids["owner.op2@crm.local"]

    await _ensure_owner(test_settings, contact_id, group_id, op1_id)
    req = await client.post(
        f"/api/v1/contacts/{contact_id}/groups/{group_id}/transfers",
        headers=ownership_op1_headers,
        json={"to_user_id": op2_id, "comment": "handoff"},
    )
    assert req.status_code == 201
    transfer_id = req.json()["id"]

    response = await client.post(
        f"/api/v1/contact-transfers/{transfer_id}/approve",
        headers=ownership_senior_headers,
        params={"expected_version": 999},
    )
    assert response.status_code == 409
