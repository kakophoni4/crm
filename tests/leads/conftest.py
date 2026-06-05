from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator

import pytest_asyncio
from sqlalchemy import create_engine, text

from app.modules.bots.hmac_util import sign_inbound
from app.shared.security.passwords import hash_password
from app.shared.settings import Settings
from tests.auth.conftest import _sync_database_url

# Dedicated 88199xxxx range — avoids bots (999001) and legacy leads ids (999882/999883).
LEADS_CYCLE_INBOUND_SECRET = "leads-cycle-inbound-32chars-minimum"
LEADS_CYCLE_BOT_CODE = "leads_cycle_bot"
LEADS_CYCLE_TELEGRAM_USER_ID = 881_990_001
LEADS_CYCLE_INBOX_PREFIX = "01LEADCYCLE"

LEADS_DEPT_INBOUND_SECRET = "dept-bot-inbound-secret-32chars"
LEADS_DEPT_BOT_CODE = "leads_dept_bot_only"
LEADS_DEPT_TELEGRAM_USER_ID = 881_990_002
LEADS_DEPT_INBOX_PREFIX = "01LEADDEPT"

LEADS_TEST_CONTACT_PATTERN = "Leads Test %"
LEADS_API_CONTACT_NAME = "Leads API Shared Contact"
LEADS_API_PASSWORD = "TestPass!234567"


def _purge_telegram_contact(
    connection: object,
    telegram_user_id: int,
    *,
    inbox_event_prefix: str | None = None,
    external_event_prefix: str | None = None,
    bot_code: str | None = None,
) -> None:
    if inbox_event_prefix:
        connection.execute(
            text("DELETE FROM bot_events_inbox WHERE event_id LIKE :prefix"),
            {"prefix": f"{inbox_event_prefix}%"},
        )
    if external_event_prefix:
        connection.execute(
            text("DELETE FROM messages WHERE external_event_id LIKE :prefix"),
            {"prefix": f"{external_event_prefix}%"},
        )
    connection.execute(
        text(
            """
            DELETE FROM messages
            WHERE chat_id IN (
                SELECT id FROM chats
                WHERE contact_id IN (
                    SELECT id FROM contacts WHERE telegram_user_id = :tg
                )
            )
            """
        ),
        {"tg": telegram_user_id},
    )
    connection.execute(
        text(
            """
            DELETE FROM leads
            WHERE contact_id IN (
                SELECT id FROM contacts WHERE telegram_user_id = :tg
            )
            """
        ),
        {"tg": telegram_user_id},
    )
    connection.execute(
        text(
            """
            DELETE FROM chats
            WHERE contact_id IN (
                SELECT id FROM contacts WHERE telegram_user_id = :tg
            )
            """
        ),
        {"tg": telegram_user_id},
    )
    connection.execute(
        text("DELETE FROM contacts WHERE telegram_user_id = :tg"),
        {"tg": telegram_user_id},
    )
    if bot_code:
        connection.execute(
            text("DELETE FROM bots WHERE code = :code"),
            {"code": bot_code},
        )


def _purge_contacts_by_name_pattern(connection: object, name_pattern: str) -> None:
    connection.execute(
        text(
            """
            DELETE FROM contact_group_assignments
            WHERE contact_id IN (
                SELECT id FROM contacts WHERE full_name LIKE :pattern
            )
            """
        ),
        {"pattern": name_pattern},
    )
    connection.execute(
        text(
            """
            DELETE FROM messages
            WHERE chat_id IN (
                SELECT id FROM chats WHERE contact_id IN (
                    SELECT id FROM contacts WHERE full_name LIKE :pattern
                )
            )
            """
        ),
        {"pattern": name_pattern},
    )
    connection.execute(
        text(
            """
            DELETE FROM leads
            WHERE contact_id IN (
                SELECT id FROM contacts WHERE full_name LIKE :pattern
            )
            """
        ),
        {"pattern": name_pattern},
    )
    connection.execute(
        text(
            """
            DELETE FROM chats
            WHERE contact_id IN (
                SELECT id FROM contacts WHERE full_name LIKE :pattern
            )
            """
        ),
        {"pattern": name_pattern},
    )
    connection.execute(
        text("DELETE FROM contacts WHERE full_name LIKE :pattern"),
        {"pattern": name_pattern},
    )


@pytest_asyncio.fixture
async def leads_org(
    alembic_config: object,
    test_settings: Settings,
    db_ready: None,
) -> AsyncIterator[dict[str, int]]:
    del alembic_config
    engine = create_engine(_sync_database_url(test_settings.database_url))
    try:
        with engine.begin() as connection:
            _purge_contacts_by_name_pattern(connection, LEADS_TEST_CONTACT_PATTERN)
            connection.execute(
                text("DELETE FROM bots WHERE code = 'leads_test_bot'"),
            )

            connection.execute(
                text(
                    """
                    INSERT INTO departments (name)
                    VALUES ('Leads Test Dept')
                    ON CONFLICT (name) DO NOTHING
                    """
                ),
            )
            dept_id = connection.execute(
                text("SELECT id FROM departments WHERE name = 'Leads Test Dept'"),
            ).scalar_one()

            connection.execute(
                text(
                    """
                    INSERT INTO groups (name, department_id)
                    VALUES ('Leads Test Group', :dept_id)
                    ON CONFLICT (department_id, name) DO NOTHING
                    """
                ),
                {"dept_id": dept_id},
            )
            group_id = connection.execute(
                text(
                    """
                    SELECT id FROM groups
                    WHERE department_id = :dept_id AND name = 'Leads Test Group'
                    """
                ),
                {"dept_id": dept_id},
            ).scalar_one()

            admin_id = connection.execute(
                text("SELECT id FROM users WHERE role = 'admin' LIMIT 1"),
            ).scalar_one()

            contact_id = connection.execute(
                text(
                    """
                    INSERT INTO contacts (full_name, created_by)
                    VALUES ('Leads Test Contact', :created_by)
                    RETURNING id
                    """
                ),
                {"created_by": admin_id},
            ).scalar_one()

            bot_id = connection.execute(
                text(
                    """
                    INSERT INTO bots (
                        code, name, owner_type, owner_id,
                        inbound_secret_encrypted, outbound_secret_encrypted, outbound_url
                    )
                    VALUES (
                        'leads_test_bot', 'Leads Test Bot', 'group', :group_id,
                        '\\x00', '\\x00', 'https://example.test/outbound'
                    )
                    ON CONFLICT (code) DO UPDATE SET owner_id = EXCLUDED.owner_id
                    RETURNING id
                    """
                ),
                {"group_id": group_id},
            ).scalar_one()

            chat_id = connection.execute(
                text(
                    """
                    INSERT INTO chats (
                        contact_id, bot_id, assigned_group_id, assigned_department_id, status
                    )
                    VALUES (:cid, :bid, :gid, :dept_id, 'open')
                    RETURNING id
                    """
                ),
                {
                    "cid": contact_id,
                    "bid": bot_id,
                    "gid": group_id,
                    "dept_id": dept_id,
                },
            ).scalar_one()
    finally:
        engine.dispose()

    yield {
        "contact_id": int(contact_id),
        "group_id": int(group_id),
        "bot_id": int(bot_id),
        "chat_id": int(chat_id),
        "dept_id": int(dept_id),
    }

    engine = create_engine(_sync_database_url(test_settings.database_url))
    try:
        with engine.begin() as connection:
            _purge_contacts_by_name_pattern(connection, LEADS_TEST_CONTACT_PATTERN)
            connection.execute(
                text("DELETE FROM bots WHERE code = 'leads_test_bot'"),
            )
    finally:
        engine.dispose()


def build_leads_cycle_inbound(
    *,
    event_id: str,
    external_message_id: str,
    text: str,
    bot_code: str = LEADS_CYCLE_BOT_CODE,
) -> tuple[bytes, dict[str, str]]:
    envelope = {
        "event": "message.received",
        "event_id": event_id,
        "occurred_at": "2026-05-17T12:00:00Z",
        "bot_code": bot_code,
        "payload": {
            "contact": {
                "telegram_user_id": LEADS_CYCLE_TELEGRAM_USER_ID,
                "telegram_username": "leads_cycle_user",
                "first_name": "Cycle",
                "last_name": "Lead",
            },
            "message": {
                "external_id": external_message_id,
                "text": text,
                "attachments": [],
                "sent_at": "2026-05-17T12:00:01Z",
            },
        },
    }
    body = json.dumps(envelope, separators=(",", ":")).encode("utf-8")
    ts = str(int(time.time()))
    headers = {
        "X-Bot-Code": bot_code,
        "X-Event-Id": event_id,
        "X-Timestamp": ts,
        "X-Signature": sign_inbound(event_id, ts, body, LEADS_CYCLE_INBOUND_SECRET),
        "Content-Type": "application/json",
    }
    return body, headers


@pytest_asyncio.fixture
async def leads_cycle_org(
    alembic_config: object,
    test_settings: Settings,
    db_ready: None,
) -> AsyncIterator[dict[str, object]]:
    del alembic_config
    password = LEADS_API_PASSWORD
    password_hash = hash_password(password)
    key = test_settings.pgcrypto_key

    def _setup_cycle_org(conn: object) -> tuple[int, int]:
        _purge_telegram_contact(
            conn,
            LEADS_CYCLE_TELEGRAM_USER_ID,
            inbox_event_prefix=LEADS_CYCLE_INBOX_PREFIX,
            external_event_prefix=LEADS_CYCLE_INBOX_PREFIX,
            bot_code=LEADS_CYCLE_BOT_CODE,
        )
        conn.execute(
            text("DELETE FROM users WHERE email = 'leads.cycle.op@crm.local'"),
        )

        conn.execute(
            text(
                """
                INSERT INTO departments (name)
                VALUES ('Leads Cycle Dept')
                ON CONFLICT (name) DO NOTHING
                """
            ),
        )
        dept_id = conn.execute(
            text("SELECT id FROM departments WHERE name = 'Leads Cycle Dept'"),
        ).scalar_one()

        conn.execute(
            text(
                """
                INSERT INTO groups (name, department_id)
                VALUES ('Leads Cycle Group', :dept_id)
                ON CONFLICT (department_id, name) DO NOTHING
                """
            ),
            {"dept_id": dept_id},
        )
        group_id = conn.execute(
            text(
                """
                SELECT id FROM groups
                WHERE department_id = :dept_id AND name = 'Leads Cycle Group'
                """
            ),
            {"dept_id": dept_id},
        ).scalar_one()

        conn.execute(
            text(
                """
                INSERT INTO users (
                    email, username, password_hash, full_name, role, group_id, department_id
                )
                VALUES (
                    'leads.cycle.op@crm.local', 'leads.cycle.op', :password_hash,
                    'Leads Cycle Operator', 'user', :group_id, :dept_id
                )
                """
            ),
            {
                "password_hash": password_hash,
                "group_id": group_id,
                "dept_id": dept_id,
            },
        )

        conn.execute(
            text(
                """
                INSERT INTO bots (
                    code, name, owner_type, owner_id,
                    inbound_secret_encrypted, outbound_secret_encrypted,
                    outbound_url, health_url, is_active
                )
                VALUES (
                    :code, 'Leads Cycle Bot', 'group', :group_id,
                    pgp_sym_encrypt(:secret, :key),
                    pgp_sym_encrypt(:secret, :key),
                    'https://example.test/outbound',
                    'https://example.test/health',
                    TRUE
                )
                """
            ),
            {
                "code": LEADS_CYCLE_BOT_CODE,
                "group_id": group_id,
                "secret": LEADS_CYCLE_INBOUND_SECRET,
                "key": key,
            },
        )
        return int(group_id), int(dept_id)

    engine = create_engine(_sync_database_url(test_settings.database_url))
    pipeline_won = 0
    try:
        with engine.begin() as conn:
            group_id, dept_id = _setup_cycle_org(conn)
            pipeline_won = int(
                conn.execute(
                    text(
                        """
                        SELECT id FROM statuses
                        WHERE code = 'won' AND kind = 'lead_pipeline'
                        LIMIT 1
                        """
                    ),
                ).scalar_one(),
            )
    finally:
        engine.dispose()

    yield {
        "password": password,
        "group_id": group_id,
        "dept_id": dept_id,
        "operator_email": "leads.cycle.op@crm.local",
        "pipeline_won": pipeline_won,
    }

    engine = create_engine(_sync_database_url(test_settings.database_url))
    try:
        with engine.begin() as conn:
            _purge_telegram_contact(
                conn,
                LEADS_CYCLE_TELEGRAM_USER_ID,
                inbox_event_prefix=LEADS_CYCLE_INBOX_PREFIX,
                external_event_prefix=LEADS_CYCLE_INBOX_PREFIX,
                bot_code=LEADS_CYCLE_BOT_CODE,
            )
            conn.execute(
                text("DELETE FROM users WHERE email = 'leads.cycle.op@crm.local'"),
            )
    finally:
        engine.dispose()


@pytest_asyncio.fixture
async def leads_api_org(
    alembic_config: object,
    test_settings: Settings,
    db_ready: None,
) -> AsyncIterator[dict[str, object]]:
    del alembic_config
    password = LEADS_API_PASSWORD
    password_hash = hash_password(password)

    engine = create_engine(_sync_database_url(test_settings.database_url))
    try:
        with engine.begin() as conn:
            _purge_contacts_by_name_pattern(conn, LEADS_API_CONTACT_NAME)
            for email in (
                "leads.api.op.a@crm.local",
                "leads.api.op.b@crm.local",
                "leads.api.senior@crm.local",
            ):
                conn.execute(text("DELETE FROM users WHERE email = :email"), {"email": email})

            conn.execute(
                text(
                    """
                    INSERT INTO departments (name)
                    VALUES ('Leads API Dept')
                    ON CONFLICT (name) DO NOTHING
                    """
                ),
            )
            dept_id = conn.execute(
                text("SELECT id FROM departments WHERE name = 'Leads API Dept'"),
            ).scalar_one()

            for name in ("Leads API Group A", "Leads API Group B"):
                conn.execute(
                    text(
                        """
                        INSERT INTO groups (name, department_id)
                        VALUES (:name, :dept_id)
                        ON CONFLICT (department_id, name) DO NOTHING
                        """
                    ),
                    {"name": name, "dept_id": dept_id},
                )
            group_a = conn.execute(
                text(
                    """
                    SELECT id FROM groups
                    WHERE department_id = :dept_id AND name = 'Leads API Group A'
                    """
                ),
                {"dept_id": dept_id},
            ).scalar_one()
            group_b = conn.execute(
                text(
                    """
                    SELECT id FROM groups
                    WHERE department_id = :dept_id AND name = 'Leads API Group B'
                    """
                ),
                {"dept_id": dept_id},
            ).scalar_one()

            admin_id = conn.execute(
                text("SELECT id FROM users WHERE role = 'admin' LIMIT 1"),
            ).scalar_one()

            for email, group_id in (
                ("leads.api.op.a@crm.local", group_a),
                ("leads.api.op.b@crm.local", group_b),
            ):
                conn.execute(
                    text(
                        """
                        INSERT INTO users (
                            email, username, password_hash, full_name,
                            role, group_id, department_id
                        )
                        VALUES (
                            :email, :username, :password_hash, :full_name,
                            'user', :group_id, :dept_id
                        )
                        """
                    ),
                    {
                        "email": email,
                        "username": email.split("@")[0],
                        "password_hash": password_hash,
                        "full_name": email,
                        "group_id": group_id,
                        "dept_id": dept_id,
                    },
                )

            conn.execute(
                text(
                    """
                    INSERT INTO users (
                        email, username, password_hash, full_name, role, department_id
                    )
                    VALUES (
                        :email, :username, :password_hash, 'Leads API Senior', 'senior', :dept_id
                    )
                    """
                ),
                {
                    "email": "leads.api.senior@crm.local",
                    "username": "leads.api.senior",
                    "password_hash": password_hash,
                    "dept_id": dept_id,
                },
            )

            contact_id = conn.execute(
                text(
                    """
                    INSERT INTO contacts (full_name, created_by, assigned_department_id)
                    VALUES ('Leads API Shared Contact', :created_by, :dept_id)
                    RETURNING id
                    """
                ),
                {"created_by": admin_id, "dept_id": dept_id},
            ).scalar_one()

            pipeline_new = conn.execute(
                text(
                    """
                    SELECT id FROM statuses
                    WHERE code = 'new' AND kind = 'lead_pipeline'
                    LIMIT 1
                    """
                ),
            ).scalar_one()
            pipeline_won = conn.execute(
                text(
                    """
                    SELECT id FROM statuses
                    WHERE code = 'won' AND kind = 'lead_pipeline'
                    LIMIT 1
                    """
                ),
            ).scalar_one()
            pipeline_lost = conn.execute(
                text(
                    """
                    SELECT id FROM statuses
                    WHERE code = 'lost' AND kind = 'lead_pipeline'
                    LIMIT 1
                    """
                ),
            ).scalar_one()

            chat_a = conn.execute(
                text(
                    """
                    INSERT INTO chats (
                        contact_id, assigned_group_id, assigned_department_id, status
                    )
                    VALUES (:cid, :gid, :dept_id, 'open')
                    RETURNING id
                    """
                ),
                {"cid": contact_id, "gid": group_a, "dept_id": dept_id},
            ).scalar_one()
            chat_ids = {"a": int(chat_a)}

            conn.execute(
                text(
                    """
                    INSERT INTO contact_group_assignments (
                        contact_id, group_id, owner_user_id, assignment_source
                    )
                    VALUES (:cid, :gid, :owner, 'manual_transfer')
                    """
                ),
                {
                    "cid": contact_id,
                    "gid": group_b,
                    "owner": admin_id,
                },
            )

            closed_a = conn.execute(
                text(
                    """
                    INSERT INTO leads (
                        contact_id, group_id, chat_id, status_id, closed_at, title
                    )
                    VALUES (:cid, :gid, :chat_id, :status_id, now() - interval '2 days', 'Closed A')
                    RETURNING id
                    """
                ),
                {
                    "cid": contact_id,
                    "gid": group_a,
                    "chat_id": chat_ids["a"],
                    "status_id": pipeline_new,
                },
            ).scalar_one()
            closed_b = conn.execute(
                text(
                    """
                    INSERT INTO leads (
                        contact_id, group_id, chat_id, status_id, closed_at, title
                    )
                    VALUES (:cid, :gid, NULL, :status_id, now() - interval '1 day', 'Closed B')
                    RETURNING id
                    """
                ),
                {
                    "cid": contact_id,
                    "gid": group_b,
                    "status_id": pipeline_new,
                },
            ).scalar_one()
            open_a = conn.execute(
                text(
                    """
                    INSERT INTO leads (
                        contact_id, group_id, chat_id, status_id, title
                    )
                    VALUES (:cid, :gid, :chat_id, :status_id, 'Open A')
                    RETURNING id
                    """
                ),
                {
                    "cid": contact_id,
                    "gid": group_a,
                    "chat_id": chat_ids["a"],
                    "status_id": pipeline_new,
                },
            ).scalar_one()
            conn.execute(
                text("UPDATE chats SET current_lead_id = :lid WHERE id = :chat_id"),
                {"lid": open_a, "chat_id": chat_ids["a"]},
            )
    finally:
        engine.dispose()

    api_org = {
        "password": password,
        "dept_id": int(dept_id),
        "group_a": int(group_a),
        "group_b": int(group_b),
        "contact_id": int(contact_id),
        "chat_ids": chat_ids,
        "lead_ids": {
            "closed_a": int(closed_a),
            "closed_b": int(closed_b),
            "open_a": int(open_a),
        },
        "pipeline_new": int(pipeline_new),
        "pipeline_won": int(pipeline_won),
        "pipeline_lost": int(pipeline_lost),
        "emails": {
            "op_a": "leads.api.op.a@crm.local",
            "op_b": "leads.api.op.b@crm.local",
            "senior": "leads.api.senior@crm.local",
        },
    }
    yield api_org

    engine = create_engine(_sync_database_url(test_settings.database_url))
    try:
        with engine.begin() as conn:
            _purge_contacts_by_name_pattern(conn, LEADS_API_CONTACT_NAME)
            for email in (
                "leads.api.op.a@crm.local",
                "leads.api.op.b@crm.local",
                "leads.api.senior@crm.local",
            ):
                conn.execute(text("DELETE FROM users WHERE email = :email"), {"email": email})
    finally:
        engine.dispose()


def build_leads_dept_inbound(
    event_id: str,
    *,
    external_message_id: str,
    text_body: str,
    bot_code: str = LEADS_DEPT_BOT_CODE,
) -> tuple[bytes, dict[str, str]]:
    envelope = {
        "event": "message.received",
        "event_id": event_id,
        "occurred_at": "2026-05-17T12:00:00Z",
        "bot_code": bot_code,
        "payload": {
            "contact": {
                "telegram_user_id": LEADS_DEPT_TELEGRAM_USER_ID,
                "telegram_username": "dept_bot_user",
                "first_name": "Dept",
                "last_name": "Bot",
            },
            "message": {
                "external_id": external_message_id,
                "text": text_body,
                "attachments": [],
                "sent_at": "2026-05-17T12:00:01Z",
            },
        },
    }
    body = json.dumps(envelope, separators=(",", ":")).encode("utf-8")
    ts = str(int(time.time()))
    return body, {
        "X-Bot-Code": bot_code,
        "X-Event-Id": event_id,
        "X-Timestamp": ts,
        "X-Signature": sign_inbound(event_id, ts, body, LEADS_DEPT_INBOUND_SECRET),
        "Content-Type": "application/json",
    }


@pytest_asyncio.fixture
async def leads_dept_bot_org(
    test_settings: Settings,
    db_ready: None,
) -> AsyncIterator[dict[str, int]]:
    del db_ready
    key = test_settings.pgcrypto_key
    engine = create_engine(_sync_database_url(test_settings.database_url))
    try:
        with engine.begin() as conn:
            _purge_telegram_contact(
                conn,
                LEADS_DEPT_TELEGRAM_USER_ID,
                inbox_event_prefix=LEADS_DEPT_INBOX_PREFIX,
                external_event_prefix=LEADS_DEPT_INBOX_PREFIX,
                bot_code=LEADS_DEPT_BOT_CODE,
            )
            dept_id = conn.execute(
                text(
                    """
                    INSERT INTO departments (name)
                    VALUES ('Leads Dept Bot Dept')
                    ON CONFLICT (name) DO NOTHING
                    RETURNING id
                    """
                ),
            ).scalar_one_or_none()
            if dept_id is None:
                dept_id = conn.execute(
                    text("SELECT id FROM departments WHERE name = 'Leads Dept Bot Dept'"),
                ).scalar_one()
            conn.execute(
                text(
                    """
                    INSERT INTO bots (
                        code, name, owner_type, owner_id,
                        inbound_secret_encrypted, outbound_secret_encrypted,
                        outbound_url, health_url, is_active
                    )
                    VALUES (
                        :code, 'Dept-only Bot', 'department', :owner_id,
                        pgp_sym_encrypt(:secret, :key),
                        pgp_sym_encrypt(:secret, :key),
                        'https://example.test/outbound',
                        'https://example.test/health',
                        TRUE
                    )
                    """
                ),
                {
                    "code": LEADS_DEPT_BOT_CODE,
                    "owner_id": dept_id,
                    "secret": LEADS_DEPT_INBOUND_SECRET,
                    "key": key,
                },
            )
            dept_id = int(dept_id)
    finally:
        engine.dispose()

    yield {"dept_id": dept_id}

    engine = create_engine(_sync_database_url(test_settings.database_url))
    try:
        with engine.begin() as conn:
            _purge_telegram_contact(
                conn,
                LEADS_DEPT_TELEGRAM_USER_ID,
                inbox_event_prefix=LEADS_DEPT_INBOX_PREFIX,
                external_event_prefix=LEADS_DEPT_INBOX_PREFIX,
                bot_code=LEADS_DEPT_BOT_CODE,
            )
    finally:
        engine.dispose()
