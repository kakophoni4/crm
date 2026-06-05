from __future__ import annotations

from httpx import AsyncClient


async def test_ws_ticket_issue(
    client: AsyncClient,
    db_ready: None,
    auth_user: dict[str, object],
) -> None:
    token = auth_user["access_token"]
    assert isinstance(token, str)
    response = await client.post(
        "/api/v1/auth/ws-ticket",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert "ticket" in body
    assert body["expires_in"] == 60
    assert isinstance(body["ticket"], str)
    assert len(body["ticket"]) > 20
