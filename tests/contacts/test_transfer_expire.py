from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine, text

from app.modules.contacts.transfer_expire import expire_stale_transfers
from app.modules.db.models.enums import TransferStatus
from app.shared.db import get_session_factory
from app.shared.settings import Settings
from app.workers.jobs.scheduler import run_periodic_maintenance
from app.workers.transfer_expire import transfer_expire_scan
from tests.auth.conftest import _sync_database_url


@pytest.mark.asyncio
async def test_expire_stale_transfers_sets_expired_and_publishes(
    db_ready: None,
    ownership_org: dict[str, object],
    test_settings: Settings,
) -> None:
    group_id = int(ownership_org["group_id"])
    contact_id = int(ownership_org["contact_ids"][0])
    user_ids = ownership_org["user_ids"]
    assert isinstance(user_ids, dict)
    op2_id = user_ids["owner.op2@crm.local"]

    engine = create_engine(_sync_database_url(test_settings.database_url))
    with engine.begin() as connection:
        transfer_id = connection.execute(
            text(
                """
                INSERT INTO contact_group_transfers (
                    contact_id, group_id, from_user_id, to_user_id, requested_by,
                    state, expires_at, created_at, updated_at
                )
                VALUES (
                    :cid, :gid, :from_uid, :to_uid, :from_uid,
                    'pending_recipient', now() - interval '1 hour',
                    now(), now()
                )
                RETURNING id
                """
            ),
            {
                "cid": contact_id,
                "gid": group_id,
                "from_uid": user_ids["owner.op1@crm.local"],
                "to_uid": op2_id,
            },
        ).scalar_one()
    engine.dispose()

    publish_path = "app.modules.contacts.transfer_expire.publish"
    with patch(publish_path, new_callable=AsyncMock) as mock_publish:
        session_factory = get_session_factory()
        async with session_factory() as session:
            result = await expire_stale_transfers(session)
            await session.commit()
        assert result.expired == 1
        topics = [call.args[0] for call in mock_publish.await_args_list]
        assert "transfer.expired" in topics
        assert "contact.transfer.expired" in topics

    engine = create_engine(_sync_database_url(test_settings.database_url))
    with engine.connect() as connection:
        state = connection.execute(
            text("SELECT state FROM contact_group_transfers WHERE id = :tid"),
            {"tid": transfer_id},
        ).scalar_one()
    engine.dispose()
    assert state == TransferStatus.EXPIRED.value


@pytest.mark.asyncio
async def test_transfer_expire_scan_worker(
    db_ready: None,
    ownership_org: dict[str, object],
    test_settings: Settings,
) -> None:
    group_id = int(ownership_org["group_id"])
    contact_id = int(ownership_org["contact_ids"][0])
    user_ids = ownership_org["user_ids"]
    assert isinstance(user_ids, dict)

    engine = create_engine(_sync_database_url(test_settings.database_url))
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO contact_group_transfers (
                    contact_id, group_id, from_user_id, to_user_id, requested_by,
                    state, expires_at, created_at, updated_at
                )
                VALUES (
                    :cid, :gid, :from_uid, :to_uid, :from_uid,
                    'pending_senior', now() - interval '1 day',
                    now(), now()
                )
                """
            ),
            {
                "cid": contact_id,
                "gid": group_id,
                "from_uid": user_ids["owner.op1@crm.local"],
                "to_uid": user_ids["owner.op2@crm.local"],
            },
        )
    engine.dispose()

    await transfer_expire_scan()

    engine = create_engine(_sync_database_url(test_settings.database_url))
    with engine.connect() as connection:
        count = connection.execute(
            text(
                """
                SELECT COUNT(*) FROM contact_group_transfers
                WHERE contact_id = :cid AND group_id = :gid AND state = 'expired'
                """
            ),
            {"cid": contact_id, "gid": group_id},
        ).scalar_one()
    engine.dispose()
    assert count >= 1


@pytest.mark.asyncio
async def test_approve_expired_transfer_returns_conflict(
    client: AsyncClient,
    db_ready: None,
    ownership_org: dict[str, object],
    ownership_senior_headers: dict[str, str],
    test_settings: Settings,
) -> None:
    group_id = int(ownership_org["group_id"])
    contact_id = int(ownership_org["contact_ids"][0])
    user_ids = ownership_org["user_ids"]
    assert isinstance(user_ids, dict)

    engine = create_engine(_sync_database_url(test_settings.database_url))
    with engine.begin() as connection:
        transfer_id = connection.execute(
            text(
                """
                INSERT INTO contact_group_transfers (
                    contact_id, group_id, from_user_id, to_user_id, requested_by,
                    state, expires_at, created_at, updated_at
                )
                VALUES (
                    :cid, :gid, :from_uid, :to_uid, :from_uid,
                    'expired', now() - interval '1 day', now(), now()
                )
                RETURNING id
                """
            ),
            {
                "cid": contact_id,
                "gid": group_id,
                "from_uid": user_ids["owner.op1@crm.local"],
                "to_uid": user_ids["owner.op2@crm.local"],
            },
        ).scalar_one()
    engine.dispose()

    response = await client.post(
        f"/api/v1/contact-transfers/{transfer_id}/approve",
        headers=ownership_senior_headers,
    )
    assert response.status_code == 409
    assert "expired" in response.json()["error"]["message"].lower()


@pytest.mark.asyncio
async def test_run_periodic_maintenance_invokes_escalation_and_expire(
    db_ready: None,
) -> None:
    with (
        patch("app.workers.escalation.escalation_scan", new_callable=AsyncMock) as mock_esc,
        patch(
            "app.workers.transfer_expire.transfer_expire_scan",
            new_callable=AsyncMock,
        ) as mock_exp,
    ):
        await run_periodic_maintenance("run_periodic_maintenance", {})
    mock_esc.assert_awaited_once()
    mock_exp.assert_awaited_once()
