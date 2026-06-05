from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest.mark.asyncio
async def test_metrics_disabled_returns_404(client: AsyncClient) -> None:
    response = await client.get("/metrics")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_metrics_enabled_exposes_prometheus(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.shared.settings import settings

    monkeypatch.setattr(settings, "metrics_enabled", True)
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        response = await http.get("/metrics")

    assert response.status_code == 200
    body = response.text
    assert "bot_events_ingest_total" in body
    assert "bot_outbound_total" in body
    assert "ws_connections_active" in body
    assert "redis_stream_pending" in body
