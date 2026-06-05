from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.parametrize(
    ("kind", "status", "code"),
    [
        ("validation", 422, "validation_error"),
        ("authentication", 401, "authentication_required"),
        ("permission", 403, "permission_denied"),
        ("not_found", 404, "not_found"),
        ("conflict", 409, "conflict"),
        ("rate_limited", 429, "rate_limited"),
    ],
)
@pytest.mark.asyncio
async def test_app_error_response_format(
    client: AsyncClient,
    kind: str,
    status: int,
    code: str,
) -> None:
    response = await client.get(f"/test/errors/{kind}")
    assert response.status_code == status
    body = response.json()
    assert "error" in body
    error = body["error"]
    assert error["code"] == code
    assert error["message"] == f"Test {kind} error"
    assert error["details"] == {"kind": kind}
    assert "request_id" in error
    assert response.headers.get("X-Request-Id") == error["request_id"]


@pytest.mark.asyncio
async def test_request_validation_error_format(client: AsyncClient) -> None:
    response = await client.post("/test/validate", json={})
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert "request_id" in body["error"]
    assert "message" in body["error"]
