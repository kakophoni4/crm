from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_contact_mutations_write_audit_log_with_request_id(
    client: AsyncClient,
    admin_headers: dict[str, str],
) -> None:
    request_id = "audit-contact-flow-01"
    headers = {**admin_headers, "X-Request-Id": request_id}

    create_resp = await client.post(
        "/api/v1/contacts",
        headers=headers,
        json={"full_name": "Audit Trail Contact"},
    )
    assert create_resp.status_code == 201, create_resp.text
    contact_id = create_resp.json()["id"]

    patch_resp = await client.patch(
        f"/api/v1/contacts/{contact_id}",
        headers={**headers, "X-Request-Id": "audit-contact-flow-02"},
        json={"full_name": "Audit Trail Contact v2"},
    )
    assert patch_resp.status_code == 200, patch_resp.text

    delete_resp = await client.delete(
        f"/api/v1/contacts/{contact_id}",
        headers={**headers, "X-Request-Id": "audit-contact-flow-03"},
    )
    assert delete_resp.status_code == 200, delete_resp.text
    assert delete_resp.json()["status"] == "archived"

    audit_resp = await client.get(f"/api/v1/contacts/{contact_id}/audit", headers=admin_headers)
    assert audit_resp.status_code == 200, audit_resp.text
    items = audit_resp.json()["items"]
    actions = {item["action"] for item in items}
    assert actions >= {"contact.create", "contact.update", "contact.delete"}
    assert any(item["request_id"] == request_id for item in items)
    assert all(item["request_id"] for item in items)
