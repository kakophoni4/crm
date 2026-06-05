from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine, text

from app.shared.settings import Settings, get_settings
from app.workers.jobs.purge_leads import purge_expired_leads
from tests.auth.conftest import _sync_database_url
from tests.chats.conftest import login


@pytest.mark.asyncio
async def test_close_lead_sets_retention_expires_at(
    client: AsyncClient,
    leads_api_org: dict[str, object],
    test_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    db_ready: None,
) -> None:
    del db_ready
    monkeypatch.setenv("LEAD_RETENTION_DAYS", "90")
    get_settings.cache_clear()

    lead_ids = leads_api_org["lead_ids"]
    assert isinstance(lead_ids, dict)
    lead_id = int(lead_ids["open_a"])

    token = await login(
        client,
        str(leads_api_org["emails"]["op_a"]),
        str(leads_api_org["password"]),
    )
    before = datetime.now(UTC)
    response = await client.post(
        f"/api/v1/leads/{lead_id}/close",
        headers={"Authorization": f"Bearer {token}"},
        json={"status_id": leads_api_org["pipeline_won"]},
    )
    assert response.status_code == 200, response.text
    after = datetime.now(UTC)

    engine = create_engine(_sync_database_url(test_settings.database_url))
    try:
        with engine.connect() as conn:
            expires = conn.execute(
                text("SELECT retention_expires_at FROM leads WHERE id = :lid"),
                {"lid": lead_id},
            ).scalar_one()
    finally:
        engine.dispose()

    assert expires is not None
    expected_min = before + timedelta(days=90)
    expected_max = after + timedelta(days=90)
    assert expected_min <= expires.replace(tzinfo=UTC) <= expected_max


@pytest.mark.asyncio
async def test_purge_job_stub_does_not_delete(
    leads_api_org: dict[str, object],
    test_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    db_ready: None,
) -> None:
    del db_ready
    monkeypatch.setenv("LEAD_PURGE_ENABLED", "false")
    get_settings.cache_clear()

    lead_ids = leads_api_org["lead_ids"]
    assert isinstance(lead_ids, dict)
    lead_id = int(lead_ids["closed_a"])

    engine = create_engine(_sync_database_url(test_settings.database_url))
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE leads
                    SET retention_expires_at = now() - interval '1 day'
                    WHERE id = :lid
                    """
                ),
                {"lid": lead_id},
            )
    finally:
        engine.dispose()

    await purge_expired_leads("purge_expired_leads", {})

    engine = create_engine(_sync_database_url(test_settings.database_url))
    try:
        with engine.connect() as conn:
            still_there = conn.execute(
                text("SELECT id FROM leads WHERE id = :lid"),
                {"lid": lead_id},
            ).scalar_one_or_none()
    finally:
        engine.dispose()

    assert still_there == lead_id


@pytest.mark.asyncio
async def test_purge_job_skips_when_enabled_without_retention_days(
    leads_api_org: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
    db_ready: None,
) -> None:
    del db_ready
    monkeypatch.setenv("LEAD_PURGE_ENABLED", "true")
    monkeypatch.delenv("LEAD_RETENTION_DAYS", raising=False)
    get_settings.cache_clear()

    lead_ids = leads_api_org["lead_ids"]
    assert isinstance(lead_ids, dict)
    lead_id = int(lead_ids["closed_a"])

    await purge_expired_leads("purge_expired_leads", {})

    engine = create_engine(_sync_database_url(get_settings().database_url))
    try:
        with engine.connect() as conn:
            still_there = conn.execute(
                text("SELECT id FROM leads WHERE id = :lid"),
                {"lid": lead_id},
            ).scalar_one_or_none()
    finally:
        engine.dispose()

    assert still_there == lead_id


@pytest.mark.asyncio
async def test_purge_job_deletes_when_enabled(
    leads_api_org: dict[str, object],
    test_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    db_ready: None,
) -> None:
    del db_ready
    monkeypatch.setenv("LEAD_PURGE_ENABLED", "true")
    monkeypatch.setenv("LEAD_RETENTION_DAYS", "90")
    get_settings.cache_clear()

    lead_ids = leads_api_org["lead_ids"]
    assert isinstance(lead_ids, dict)
    lead_id = int(lead_ids["closed_a"])

    engine = create_engine(_sync_database_url(test_settings.database_url))
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE leads
                    SET retention_expires_at = now() - interval '1 day',
                        closed_at = COALESCE(closed_at, now() - interval '2 days')
                    WHERE id = :lid
                    """
                ),
                {"lid": lead_id},
            )
            message_id = conn.execute(
                text(
                    """
                    INSERT INTO messages (
                        chat_id, lead_id, direction, kind, text
                    )
                    SELECT chat_id, :lid, 'inbound', 'text', 'purge fixture'
                    FROM leads WHERE id = :lid
                    RETURNING id
                    """
                ),
                {"lid": lead_id},
            ).scalar_one()
    finally:
        engine.dispose()

    await purge_expired_leads("purge_expired_leads", {})

    engine = create_engine(_sync_database_url(test_settings.database_url))
    try:
        with engine.connect() as conn:
            lead_row = conn.execute(
                text("SELECT id FROM leads WHERE id = :lid"),
                {"lid": lead_id},
            ).scalar_one_or_none()
            msg_lead_id = conn.execute(
                text("SELECT lead_id FROM messages WHERE id = :mid"),
                {"mid": message_id},
            ).scalar_one()
    finally:
        engine.dispose()

    assert lead_row is None
    assert msg_lead_id is None
