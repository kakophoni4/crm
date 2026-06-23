from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine, text

from tests.auth.conftest import _sync_database_url


@pytest.mark.asyncio
async def test_admin_creates_bitcall_telephony_account_without_leaking_password(
    client: AsyncClient,
    db_ready: None,
    admin_headers: dict[str, str],
    bots_org: dict[str, object],
    test_settings,
) -> None:
    dept_id = int(bots_org["dept_id"])
    group_id = int(bots_org["group_id"])
    sip_password = "bitcall-sip-password"

    response = await client.post(
        "/api/v1/telephony/accounts",
        headers=admin_headers,
        json={
            "name": "Bitcall Main",
            "provider": "bitcall",
            "department_id": dept_id,
            "group_id": group_id,
            "sip_host": "sip.bitcall.example",
            "sip_port": 5060,
            "sip_transport": "udp",
            "sip_username": "100200300",
            "sip_password": sip_password,
            "outbound_caller_id": "+79005550123",
            "pbx_extension_prefix": "7",
            "webrtc_ws_url": "wss://pbx.example.test/ws",
        },
    )

    assert response.status_code == 201, response.text
    assert sip_password not in response.text
    body = response.json()
    assert body["provider"] == "bitcall"
    assert body["group_id"] == group_id
    assert body["has_sip_password"] is True
    assert body["webrtc_ws_url"] == "wss://pbx.example.test/ws"

    engine = create_engine(_sync_database_url(test_settings.database_url))
    try:
        with engine.connect() as connection:
            decrypted = connection.execute(
                text(
                    """
                    SELECT pgp_sym_decrypt(sip_password_encrypted, :key)
                    FROM telephony_accounts
                    WHERE id = :id
                    """
                ),
                {"id": body["id"], "key": test_settings.pgcrypto_key},
            ).scalar_one()
    finally:
        engine.dispose()

    assert decrypted == sip_password


@pytest.mark.asyncio
async def test_operator_lists_visible_telephony_accounts(
    client: AsyncClient,
    db_ready: None,
    admin_headers: dict[str, str],
    operator_headers: dict[str, str],
    bots_org: dict[str, object],
) -> None:
    dept_id = int(bots_org["dept_id"])
    group_id = int(bots_org["group_id"])
    created = await client.post(
        "/api/v1/telephony/accounts",
        headers=admin_headers,
        json={
            "name": "Bitcall Visible",
            "department_id": dept_id,
            "group_id": group_id,
            "sip_host": "sip.bitcall.example",
            "sip_username": "visible-user",
            "sip_password": "visible-password",
        },
    )
    assert created.status_code == 201, created.text

    response = await client.get("/api/v1/telephony/accounts", headers=operator_headers)
    assert response.status_code == 200, response.text
    names = {item["name"] for item in response.json()["items"]}
    assert "Bitcall Visible" in names
    assert "visible-password" not in response.text


@pytest.mark.asyncio
async def test_admin_assigns_telephony_account_to_multiple_groups(
    client: AsyncClient,
    db_ready: None,
    admin_headers: dict[str, str],
    bots_org: dict[str, object],
    test_settings,
) -> None:
    dept_id = int(bots_org["dept_id"])
    group_id = int(bots_org["group_id"])

    engine = create_engine(_sync_database_url(test_settings.database_url))
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO groups (name, department_id)
                    VALUES ('Bots Test Group B', :dept_id)
                    ON CONFLICT (department_id, name) DO NOTHING
                    """
                ),
                {"dept_id": dept_id},
            )
            second_group_id = connection.execute(
                text(
                    """
                    SELECT id FROM groups
                    WHERE department_id = :dept_id AND name = 'Bots Test Group B'
                    """
                ),
                {"dept_id": dept_id},
            ).scalar_one()
    finally:
        engine.dispose()

    response = await client.post(
        "/api/v1/telephony/accounts",
        headers=admin_headers,
        json={
            "name": "Bitcall Multi Group",
            "department_id": dept_id,
            "group_ids": [group_id, second_group_id],
            "sip_host": "sip.bitcall.example",
            "sip_username": "multi-group-user",
            "sip_password": "multi-group-password",
        },
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert set(body["group_ids"]) == {group_id, second_group_id}
    assert set(body["group_names"]) == {"Bots Test Group", "Bots Test Group B"}


@pytest.mark.asyncio
async def test_admin_updates_and_deactivates_telephony_account(
    client: AsyncClient,
    db_ready: None,
    admin_headers: dict[str, str],
    bots_org: dict[str, object],
) -> None:
    dept_id = int(bots_org["dept_id"])
    created = await client.post(
        "/api/v1/telephony/accounts",
        headers=admin_headers,
        json={
            "name": "Bitcall To Update",
            "department_id": dept_id,
            "sip_host": "sip.bitcall.example",
            "sip_username": "update-user",
            "sip_password": "initial-password",
        },
    )
    assert created.status_code == 201, created.text
    account_id = created.json()["id"]

    updated = await client.patch(
        f"/api/v1/telephony/accounts/{account_id}",
        headers=admin_headers,
        json={
            "name": "Bitcall Updated",
            "sip_transport": "tls",
            "sip_password": "rotated-password",
            "is_active": True,
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "Bitcall Updated"
    assert updated.json()["sip_transport"] == "tls"
    assert "rotated-password" not in updated.text

    deleted = await client.delete(
        f"/api/v1/telephony/accounts/{account_id}",
        headers=admin_headers,
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["is_active"] is False


@pytest.mark.asyncio
async def test_operator_gets_internal_webrtc_extension_not_bitcall_password(
    client: AsyncClient,
    db_ready: None,
    admin_headers: dict[str, str],
    operator_headers: dict[str, str],
    bots_org: dict[str, object],
) -> None:
    dept_id = int(bots_org["dept_id"])
    group_id = int(bots_org["group_id"])
    sip_password = "provider-secret-never-to-browser"
    created = await client.post(
        "/api/v1/telephony/accounts",
        headers=admin_headers,
        json={
            "name": "Bitcall WebRTC",
            "department_id": dept_id,
            "group_id": group_id,
            "sip_host": "sip.bitcall.example",
            "sip_username": "webrtc-user",
            "sip_password": sip_password,
            "pbx_extension_prefix": "71",
            "webrtc_ws_url": "ws://127.0.0.1:8088/ws",
        },
    )
    assert created.status_code == 201, created.text
    account_id = created.json()["id"]

    first = await client.post(
        f"/api/v1/telephony/accounts/{account_id}/webrtc-config",
        headers=operator_headers,
    )
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["account_id"] == account_id
    assert body["extension"].startswith("71")
    assert body["extension_password"]
    assert body["extension_password"] != sip_password
    assert sip_password not in first.text
    assert body["sip_uri"] == f"sip:{body['extension']}@127.0.0.1"
    assert body["ws_url"] == "ws://127.0.0.1:8088/ws"

    second = await client.post(
        f"/api/v1/telephony/accounts/{account_id}/webrtc-config",
        headers=operator_headers,
    )
    assert second.status_code == 200, second.text
    assert second.json()["extension"] == body["extension"]
    assert second.json()["extension_password"] == body["extension_password"]


@pytest.mark.asyncio
async def test_telephony_call_history_is_scoped_by_role(
    client: AsyncClient,
    db_ready: None,
    admin_headers: dict[str, str],
    operator_headers: dict[str, str],
    senior_headers: dict[str, str],
    bots_org: dict[str, object],
    test_settings,
) -> None:
    dept_id = int(bots_org["dept_id"])
    group_id = int(bots_org["group_id"])
    created = await client.post(
        "/api/v1/telephony/accounts",
        headers=admin_headers,
        json={
            "name": "Bitcall History",
            "department_id": dept_id,
            "group_id": group_id,
            "sip_host": "sip.bitcall.example",
            "sip_username": "history-user",
            "sip_password": "history-secret",
            "webrtc_ws_url": "ws://127.0.0.1:8088/ws",
        },
    )
    assert created.status_code == 201, created.text
    account_id = created.json()["id"]

    started = await client.post(
        "/api/v1/telephony/calls",
        headers=operator_headers,
        json={"account_id": account_id, "phone_number": "9001112233"},
    )
    assert started.status_code == 201, started.text
    call = started.json()
    assert call["phone_number"] == "+79001112233"

    completed = await client.patch(
        f"/api/v1/telephony/calls/{call['id']}",
        headers=operator_headers,
        json={"status": "completed", "duration_seconds": 12},
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["duration_seconds"] == 12

    engine = create_engine(_sync_database_url(test_settings.database_url))
    try:
        with engine.begin() as connection:
            other_dept_id = connection.execute(
                text(
                    """
                    INSERT INTO departments (name)
                    VALUES ('Telephony Other Dept')
                    ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
                    RETURNING id
                    """
                ),
            ).scalar_one()
            other_group_id = connection.execute(
                text(
                    """
                    INSERT INTO groups (name, department_id)
                    VALUES ('Telephony Other Group', :dept_id)
                    ON CONFLICT (department_id, name) DO UPDATE SET name = EXCLUDED.name
                    RETURNING id
                    """
                ),
                {"dept_id": other_dept_id},
            ).scalar_one()
            other_user_id = connection.execute(
                text(
                    """
                    INSERT INTO users (
                        email, username, password_hash, full_name, role, department_id, group_id
                    )
                    VALUES (
                        'telephony.other@crm.local',
                        'telephony.other',
                        'hash',
                        'Telephony Other',
                        'user',
                        :dept_id,
                        :group_id
                    )
                    ON CONFLICT (email) DO UPDATE
                    SET department_id = EXCLUDED.department_id,
                        group_id = EXCLUDED.group_id
                    RETURNING id
                    """
                ),
                {"dept_id": other_dept_id, "group_id": other_group_id},
            ).scalar_one()
            other_account_id = connection.execute(
                text(
                    """
                    INSERT INTO telephony_accounts (
                        name, provider, department_id, sip_host, sip_username,
                        sip_password_encrypted, is_active
                    )
                    VALUES (
                        'Bitcall Other',
                        'bitcall',
                        :dept_id,
                        'sip.bitcall.example',
                        'other-user',
                        pgp_sym_encrypt('other-secret', :key),
                        TRUE
                    )
                    RETURNING id
                    """
                ),
                {"dept_id": other_dept_id, "key": test_settings.pgcrypto_key},
            ).scalar_one()
            connection.execute(
                text(
                    """
                    INSERT INTO telephony_calls (
                        account_id, user_id, department_id, phone_number, status
                    )
                    VALUES (:account_id, :user_id, :dept_id, '+79009998877', 'completed')
                    """
                ),
                {
                    "account_id": other_account_id,
                    "user_id": other_user_id,
                    "dept_id": other_dept_id,
                },
            )
    finally:
        engine.dispose()

    operator_history = await client.get("/api/v1/telephony/calls", headers=operator_headers)
    assert operator_history.status_code == 200, operator_history.text
    assert [item["id"] for item in operator_history.json()["items"]] == [call["id"]]

    senior_history = await client.get("/api/v1/telephony/calls", headers=senior_headers)
    assert senior_history.status_code == 200, senior_history.text
    senior_numbers = {item["phone_number"] for item in senior_history.json()["items"]}
    assert "+79001112233" in senior_numbers
    assert "+79009998877" not in senior_numbers

    admin_history = await client.get("/api/v1/telephony/calls", headers=admin_headers)
    assert admin_history.status_code == 200, admin_history.text
    admin_numbers = {item["phone_number"] for item in admin_history.json()["items"]}
    assert {"+79001112233", "+79009998877"}.issubset(admin_numbers)
