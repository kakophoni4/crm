from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine, text

from tests.auth.conftest import _sync_database_url
from tests.bots.conftest import INBOUND_SECRET


@pytest.mark.asyncio
async def test_contact_detail_lists_linked_bots(
    client: AsyncClient,
    db_ready: None,
    test_settings,
    bots_org: dict[str, object],
    admin_headers: dict[str, str],
) -> None:
    engine = create_engine(_sync_database_url(test_settings.database_url))
    dept_id = int(bots_org["dept_id"])
    group_id = int(bots_org["group_id"])
    bot_a_id = int(bots_org["bot_id"])
    key = test_settings.pgcrypto_key

    try:
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM chats WHERE contact_id IN (SELECT id FROM contacts WHERE telegram_user_id = 999004)"))
            connection.execute(text("DELETE FROM contacts WHERE telegram_user_id = 999004"))
            connection.execute(text("DELETE FROM bots WHERE code = 'test_bot_linked_b'"))

            connection.execute(
                text(
                    """
                    INSERT INTO bots (
                        code, name, owner_type, owner_id, department_id,
                        inbound_secret_encrypted, outbound_secret_encrypted,
                        outbound_url, is_active
                    )
                    VALUES (
                        'test_bot_linked_b', 'Linked Bot B',
                        'group', :group_id, :dept_id,
                        pgp_sym_encrypt(:in_secret, :key),
                        pgp_sym_encrypt(:out_secret, :key),
                        'https://bot.example.com/crm/cmd',
                        TRUE
                    )
                    """
                ),
                {
                    "group_id": group_id,
                    "dept_id": dept_id,
                    "in_secret": INBOUND_SECRET,
                    "out_secret": "test-outbound-secret-32chars-minimum",
                    "key": key,
                },
            )
            bot_b_id = connection.execute(
                text("SELECT id FROM bots WHERE code = 'test_bot_linked_b'"),
            ).scalar_one()

            admin_id = connection.execute(
                text("SELECT id FROM users WHERE role = 'admin' ORDER BY id LIMIT 1"),
            ).scalar_one()
            contact_id = connection.execute(
                text(
                    """
                    INSERT INTO contacts (telegram_user_id, full_name, created_by)
                    VALUES (999004, 'Linked Bots Contact', :uid)
                    RETURNING id
                    """
                ),
                {"uid": admin_id},
            ).scalar_one()

            connection.execute(
                text(
                    """
                    INSERT INTO chats (contact_id, bot_id, assigned_group_id, assigned_department_id, status)
                    VALUES
                        (:cid, :bot_a, :gid, :dept, 'open'),
                        (:cid, :bot_b, :gid, :dept, 'open')
                    """
                ),
                {
                    "cid": contact_id,
                    "bot_a": bot_a_id,
                    "bot_b": bot_b_id,
                    "gid": group_id,
                    "dept": dept_id,
                },
            )
    finally:
        engine.dispose()

    detail = await client.get(f"/api/v1/contacts/{contact_id}", headers=admin_headers)
    assert detail.status_code == 200
    linked = detail.json()["linked_bots"]
    assert len(linked) == 2
    codes = {item["bot_code"] for item in linked}
    assert codes == {"test_bot_a", "test_bot_linked_b"}
    assert all(item["chat_id"] > 0 for item in linked)
