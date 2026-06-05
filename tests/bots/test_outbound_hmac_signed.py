from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.modules.bots.hmac_util import outbound_path_from_url, sign_outbound
from app.workers.bots.dispatch_outbound import dispatch_outbound_command, enqueue_outbound
from tests.bots.conftest import OUTBOUND_SECRET


@pytest.mark.asyncio
async def test_outbound_request_includes_hmac_headers(
    db_ready: None,
    bots_org: dict[str, object],
) -> None:
    bot_id = int(bots_org["bot_id"])
    log_id = await enqueue_outbound(
        bot_id=bot_id,
        command="send_message",
        payload={"text": "hi"},
        request_id="01J5HMACOUT0001",
    )

    captured: dict[str, object] = {}

    async def fake_post(url, *, content, headers, **_kwargs):
        captured["url"] = url
        captured["content"] = content
        captured["headers"] = headers
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"status": "ok"}
        response.request = MagicMock()
        return response

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post = fake_post
        mock_client_cls.return_value = mock_client

        await dispatch_outbound_command("dispatch_outbound", {"outbound_log_id": log_id})

    headers = captured["headers"]
    assert headers is not None
    assert "X-CRM-Signature" in headers
    assert str(headers["X-CRM-Signature"]).startswith("sha256=")

    body = captured["content"]
    assert isinstance(body, bytes)
    ts = str(headers["X-CRM-Timestamp"])
    path = outbound_path_from_url("https://bot.example.com/crm/cmd")
    expected = sign_outbound("POST", path, ts, body, OUTBOUND_SECRET)
    assert headers["X-CRM-Signature"] == expected
