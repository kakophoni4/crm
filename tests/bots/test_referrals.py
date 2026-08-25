from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine, text

from app.workers.bots.process_event import process_bot_event
from tests.auth.conftest import _sync_database_url
from tests.bots.conftest import build_inbound_payload

REFERRER_TG = 999410
REFERRED_TG = 999411
OTHER_TG = 999412


async def _accept_and_process(
    client: AsyncClient,
    *,
    event_id: str,
    telegram_user_id: int,
    text: str = "hello",
    ref_code: str | None = None,
    external_id: str | None = None,
) -> None:
    body, headers = build_inbound_payload(
        event_id=event_id,
        external_id=external_id or event_id,
        text=text,
        telegram_user_id=telegram_user_id,
        ref_code=ref_code,
    )
    with patch("app.modules.bots.service.enqueue", new_callable=AsyncMock):
        response = await client.post("/api/v1/bot-events", content=body, headers=headers)
    assert response.status_code == 202, response.text
    await process_bot_event("process_bot_event", {"event_id": event_id})


def _cleanup(engine, bot_id: int) -> None:
    with engine.begin() as connection:
        connection.execute(
            text("DELETE FROM contact_referrals WHERE bot_id = :bid"),
            {"bid": bot_id},
        )
        connection.execute(
            text("DELETE FROM contact_referral_codes WHERE bot_id = :bid"),
            {"bid": bot_id},
        )
        connection.execute(
            text(
                """
                DELETE FROM messages
                WHERE chat_id IN (
                    SELECT c.id FROM chats c
                    JOIN contacts ct ON ct.id = c.contact_id
                    WHERE ct.telegram_user_id IN (:a, :b, :c)
                )
                """
            ),
            {"a": REFERRER_TG, "b": REFERRED_TG, "c": OTHER_TG},
        )
        connection.execute(
            text(
                """
                DELETE FROM leads
                WHERE contact_id IN (
                    SELECT id FROM contacts
                    WHERE telegram_user_id IN (:a, :b, :c)
                )
                """
            ),
            {"a": REFERRER_TG, "b": REFERRED_TG, "c": OTHER_TG},
        )
        connection.execute(
            text(
                """
                DELETE FROM contact_group_assignments
                WHERE contact_id IN (
                    SELECT id FROM contacts
                    WHERE telegram_user_id IN (:a, :b, :c)
                )
                """
            ),
            {"a": REFERRER_TG, "b": REFERRED_TG, "c": OTHER_TG},
        )
        connection.execute(
            text(
                """
                DELETE FROM chats
                WHERE contact_id IN (
                    SELECT id FROM contacts
                    WHERE telegram_user_id IN (:a, :b, :c)
                )
                """
            ),
            {"a": REFERRER_TG, "b": REFERRED_TG, "c": OTHER_TG},
        )
        connection.execute(
            text("DELETE FROM contacts WHERE telegram_user_id IN (:a, :b, :c)"),
            {"a": REFERRER_TG, "b": REFERRED_TG, "c": OTHER_TG},
        )
        connection.execute(
            text(
                """
                UPDATE bots
                SET referrals_enabled = false, telegram_username = NULL
                WHERE id = :bid
                """
            ),
            {"bid": bot_id},
        )


@pytest.mark.asyncio
async def test_referral_counts_only_owned_codes(
    client: AsyncClient,
    db_ready: None,
    test_settings,
    admin_headers: dict[str, str],
    bots_org: dict[str, object],
) -> None:
    bot_id = int(bots_org["bot_id"])
    engine = create_engine(_sync_database_url(test_settings.database_url))
    try:
        _cleanup(engine, bot_id)
        denied = await client.patch(
            f"/api/v1/bots/{bot_id}",
            headers=admin_headers,
            json={"referrals_enabled": True},
        )
        assert denied.status_code == 422, denied.text

        enabled = await client.patch(
            f"/api/v1/bots/{bot_id}",
            headers=admin_headers,
            json={"referrals_enabled": True, "telegram_username": "timeletterer_bot"},
        )
        assert enabled.status_code == 200, enabled.text
        assert enabled.json()["referrals_enabled"] is True
        assert enabled.json()["telegram_username"] == "timeletterer_bot"

        await _accept_and_process(
            client,
            event_id="ref-owner-1",
            telegram_user_id=REFERRER_TG,
        )
        with engine.connect() as connection:
            chat_id = connection.execute(
                text(
                    """
                    SELECT c.id
                    FROM chats c
                    JOIN contacts ct ON ct.id = c.contact_id
                    WHERE ct.telegram_user_id = :tg AND c.bot_id = :bid
                    """
                ),
                {"tg": REFERRER_TG, "bid": bot_id},
            ).scalar_one()

        first = await client.get(f"/api/v1/chats/{chat_id}/referral", headers=admin_headers)
        assert first.status_code == 200, first.text
        payload = first.json()
        assert payload["enabled"] is True
        assert payload["count"] == 0
        assert payload["url"] == f"https://t.me/timeletterer_bot?start={payload['code']}"
        code = payload["code"]
        assert code

        await _accept_and_process(
            client,
            event_id="ref-guest-1",
            telegram_user_id=REFERRED_TG,
            ref_code=code,
        )
        counted = await client.get(f"/api/v1/chats/{chat_id}/referral", headers=admin_headers)
        assert counted.json()["count"] == 1

        await _accept_and_process(
            client,
            event_id="ref-guest-dup",
            telegram_user_id=REFERRED_TG,
            ref_code=code,
        )
        await _accept_and_process(
            client,
            event_id="ref-unknown",
            telegram_user_id=OTHER_TG,
            ref_code="zzzzzzzzzzzzzzzz",
        )
        again = await client.get(f"/api/v1/chats/{chat_id}/referral", headers=admin_headers)
        assert again.json()["count"] == 1
    finally:
        _cleanup(engine, bot_id)
        engine.dispose()


@pytest.mark.asyncio
async def test_referral_ignored_when_disabled(
    client: AsyncClient,
    db_ready: None,
    test_settings,
    admin_headers: dict[str, str],
    bots_org: dict[str, object],
) -> None:
    bot_id = int(bots_org["bot_id"])
    engine = create_engine(_sync_database_url(test_settings.database_url))
    try:
        _cleanup(engine, bot_id)
        await client.patch(
            f"/api/v1/bots/{bot_id}",
            headers=admin_headers,
            json={"referrals_enabled": True, "telegram_username": "timeletterer_bot"},
        )
        await _accept_and_process(client, event_id="ref-off-owner", telegram_user_id=REFERRER_TG)
        with engine.connect() as connection:
            chat_id = connection.execute(
                text(
                    """
                    SELECT c.id
                    FROM chats c
                    JOIN contacts ct ON ct.id = c.contact_id
                    WHERE ct.telegram_user_id = :tg AND c.bot_id = :bid
                    """
                ),
                {"tg": REFERRER_TG, "bid": bot_id},
            ).scalar_one()
        code = (
            await client.get(f"/api/v1/chats/{chat_id}/referral", headers=admin_headers)
        ).json()["code"]
        await client.patch(
            f"/api/v1/bots/{bot_id}",
            headers=admin_headers,
            json={"referrals_enabled": False},
        )
        await _accept_and_process(
            client,
            event_id="ref-off-guest",
            telegram_user_id=REFERRED_TG,
            ref_code=code,
        )
        hidden = await client.get(f"/api/v1/chats/{chat_id}/referral", headers=admin_headers)
        assert hidden.json()["enabled"] is False
        with engine.connect() as connection:
            count = connection.execute(
                text("SELECT count(*) FROM contact_referrals WHERE bot_id = :bid"),
                {"bid": bot_id},
            ).scalar_one()
        assert int(count) == 0
    finally:
        _cleanup(engine, bot_id)
        engine.dispose()
