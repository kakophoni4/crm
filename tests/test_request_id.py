from __future__ import annotations

import pytest
from httpx import AsyncClient
from structlog.testing import capture_logs


@pytest.mark.asyncio
async def test_request_id_echoed_from_header(client: AsyncClient) -> None:
    request_id = "01JTESTREQUESTID0000000001"
    response = await client.get("/test/request-id", headers={"X-Request-Id": request_id})
    assert response.status_code == 200
    assert response.headers.get("X-Request-Id") == request_id


@pytest.mark.asyncio
async def test_request_id_generated_when_missing(client: AsyncClient) -> None:
    response = await client.get("/test/request-id")
    assert response.status_code == 200
    request_id = response.headers.get("X-Request-Id")
    assert request_id
    assert len(request_id) == 26


@pytest.mark.asyncio
async def test_request_id_in_logs(client: AsyncClient) -> None:
    request_id = "01JTESTREQUESTID0000000002"
    with capture_logs() as logs:
        response = await client.get("/test/request-id", headers={"X-Request-Id": request_id})
    assert response.status_code == 200
    probe_logs = [entry for entry in logs if entry.get("event") == "request_id_probe"]
    assert probe_logs
    assert probe_logs[0].get("request_id") == request_id
