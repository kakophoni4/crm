from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.modules.leads.rate_limit import reset_in_memory_rate_limits
from app.shared.settings import get_settings
from tests.chats.conftest import login


@pytest.mark.asyncio
async def test_leads_list_rate_limit_429(
    client: AsyncClient,
    leads_api_org: dict[str, object],
    db_ready: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del db_ready
    emails = leads_api_org["emails"]
    assert isinstance(emails, dict)
    contact_id = leads_api_org["contact_id"]
    token = await login(client, str(emails["op_a"]), str(leads_api_org["password"]))
    headers = {"Authorization": f"Bearer {token}"}

    monkeypatch.setenv("LEADS_LIST_RATE_LIMIT_PER_MINUTE", "3")
    monkeypatch.setenv("LEADS_RATE_LIMIT_USE_REDIS", "false")
    get_settings.cache_clear()
    reset_in_memory_rate_limits()

    try:
        for _ in range(3):
            ok = await client.get(
                f"/api/v1/contacts/{contact_id}/leads",
                headers=headers,
            )
            assert ok.status_code == 200, ok.text

        limited = await client.get(
            f"/api/v1/contacts/{contact_id}/leads",
            headers=headers,
        )
        assert limited.status_code == 429, limited.text
        assert limited.json()["error"]["code"] == "rate_limited"
    finally:
        reset_in_memory_rate_limits()
        get_settings.cache_clear()
