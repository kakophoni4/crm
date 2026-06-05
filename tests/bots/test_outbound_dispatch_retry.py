from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.modules.db.models.enums import BotOutboundStatus
from app.shared.db import get_session_factory
from app.workers.bots.dispatch_outbound import dispatch_outbound_command, enqueue_outbound


@pytest.mark.asyncio
async def test_outbound_500_retries_then_sent(db_ready: None, bots_org: dict[str, object]) -> None:
    bot_id = int(bots_org["bot_id"])
    log_id = await enqueue_outbound(
        bot_id=bot_id,
        command="send_message",
        payload={"internal_id": 1, "contact": {"telegram_user_id": 999001}},
        request_id="01J5OUTBOUND001",
    )

    fail_response = MagicMock()
    fail_response.status_code = 500
    fail_response.request = MagicMock()
    fail_response.json.return_value = {"status": "error"}

    ok_response = MagicMock()
    ok_response.status_code = 200
    ok_response.request = MagicMock()
    ok_response.json.return_value = {"status": "ok", "external_id": "ext_1"}

    call_count = 0

    async def fake_post(*_args, **_kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise httpx.HTTPStatusError("fail", request=MagicMock(), response=fail_response)
        return ok_response

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post = fake_post
        mock_client_cls.return_value = mock_client

        await dispatch_outbound_command("dispatch_outbound", {"outbound_log_id": log_id})
        await dispatch_outbound_command("dispatch_outbound", {"outbound_log_id": log_id})

    session_factory = get_session_factory()
    async with session_factory() as session:
        from app.modules.bots.repository import BotOutboundLogRepository

        row = await BotOutboundLogRepository(session).get_by_id(log_id)
        assert row is not None
        assert row.status == BotOutboundStatus.SENT
        assert row.attempts >= 2
