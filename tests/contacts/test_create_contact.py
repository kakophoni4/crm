from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_contact_as_admin(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    response = await client.post(
        "/api/v1/contacts",
        headers={**admin_headers, "X-Request-Id": "test-create-contact-01"},
        json={
            "full_name": "New Contact",
            "phone": "+79001234567",
            "email": "new@example.com",
            "telegram_user_id": 100001,
            "telegram_username": "new_contact",
            "custom_fields": {"city": "Moscow"},
            "source": "manual",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["full_name"] == "New Contact"
    assert body["custom_fields"]["city"] == "Moscow"
    assert body["status"] == "new"
    assert body["telegram_user_id"] == 100001
