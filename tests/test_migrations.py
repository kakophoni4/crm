from __future__ import annotations

import os
from pathlib import Path

import bcrypt as _bcrypt
import pytest
from alembic.config import Config
from sqlalchemy import create_engine, text

from alembic import command

PROJECT_ROOT = Path(__file__).resolve().parents[1]

_OWNERSHIP_REVISIONS: tuple[tuple[str, str | None], ...] = (
    ("0012_contact_group_ownership", "0011_bot_events_outbound"),
    ("0013_group_escalation_settings", "0012_contact_group_ownership"),
    ("0014_message_reply_audit", "0013_group_escalation_settings"),
    ("0015_cgt_active_uq", "0014_message_reply_audit"),
    ("0016_messages_fts_ru", "0015_cgt_active_uq"),
    ("0017_chat_read_state", "0016_messages_fts_ru"),
    ("0018_cgt_version", "0017_chat_read_state"),
)


def _sync_database_url(database_url: str) -> str:
    for prefix in ("postgresql+asyncpg://", "postgresql+psycopg2://", "postgresql://"):
        if database_url.startswith(prefix):
            return "postgresql+psycopg://" + database_url.removeprefix(prefix)
    return database_url


def _reset_public_schema(alembic_config: Config) -> None:
    engine = create_engine(_sync_database_url(alembic_config.get_main_option("sqlalchemy.url")))
    try:
        with engine.begin() as connection:
            connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            connection.execute(text("CREATE SCHEMA public"))
            connection.execute(text("GRANT ALL ON SCHEMA public TO public"))
    finally:
        engine.dispose()


@pytest.fixture
def alembic_config(test_settings) -> Config:
    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", _sync_database_url(test_settings.database_url))
    return cfg


def test_upgrade_head_then_downgrade_to_base(alembic_config: Config) -> None:
    _reset_public_schema(alembic_config)
    command.upgrade(alembic_config, "head")
    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "head")


def test_seed_admin_present(alembic_config: Config) -> None:
    _reset_public_schema(alembic_config)
    command.upgrade(alembic_config, "head")

    engine = create_engine(_sync_database_url(alembic_config.get_main_option("sqlalchemy.url")))
    try:
        with engine.connect() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT email, password_hash, role::text
                    FROM users
                    WHERE role = 'admin'
                    """
                ),
            ).fetchall()

        assert len(rows) == 1
        email, password_hash, role = rows[0]
        expected_email = os.getenv("SEED_ADMIN_EMAIL", "admin@crm.local")
        expected_password = os.getenv("SEED_ADMIN_PASSWORD", "ChangeMe!234567")
        assert email == expected_email
        assert role == "admin"
        assert _bcrypt.checkpw(expected_password.encode("utf-8"), password_hash.encode("utf-8"))
    finally:
        engine.dispose()


@pytest.mark.parametrize(("revision", "down_revision"), _OWNERSHIP_REVISIONS)
def test_ownership_migrations_upgrade_downgrade(
    alembic_config: Config,
    revision: str,
    down_revision: str | None,
) -> None:
    _reset_public_schema(alembic_config)
    command.upgrade(alembic_config, down_revision or "base")
    command.upgrade(alembic_config, revision)
    _assert_ownership_revision_schema(alembic_config, revision)
    command.downgrade(alembic_config, down_revision or "base")
    _assert_ownership_revision_dropped(alembic_config, revision)


def _assert_ownership_revision_schema(alembic_config: Config, revision: str) -> None:
    engine = create_engine(_sync_database_url(alembic_config.get_main_option("sqlalchemy.url")))
    try:
        with engine.connect() as connection:
            if revision == "0012_contact_group_ownership":
                row = connection.execute(
                    text(
                        """
                        SELECT 1
                        FROM information_schema.tables
                        WHERE table_schema = 'public'
                          AND table_name = 'contact_group_assignments'
                        """
                    ),
                ).fetchone()
                assert row is not None
                col = connection.execute(
                    text(
                        """
                        SELECT column_name
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = 'chats'
                          AND column_name = 'last_handled_by_user_id'
                        """
                    ),
                ).fetchone()
                assert col is not None
            elif revision == "0013_group_escalation_settings":
                group_count = connection.execute(
                    text("SELECT COUNT(*)::int FROM groups"),
                ).scalar_one()
                settings_count = connection.execute(
                    text("SELECT COUNT(*)::int FROM group_escalation_settings"),
                ).scalar_one()
                assert settings_count == group_count
                if settings_count > 0:
                    timeout, strategy = connection.execute(
                        text(
                            """
                            SELECT first_response_timeout_minutes,
                                   new_contact_reassign_strategy
                            FROM group_escalation_settings
                            LIMIT 1
                            """
                        ),
                    ).one()
                    assert timeout == 15
                    assert strategy == "first_responder"
            elif revision == "0014_message_reply_audit":
                for table in ("message_reply_audit", "contact_group_transfers"):
                    row = connection.execute(
                        text(
                            """
                            SELECT 1
                            FROM information_schema.tables
                            WHERE table_schema = 'public'
                              AND table_name = :table_name
                            """
                        ),
                        {"table_name": table},
                    ).fetchone()
                    assert row is not None
            elif revision == "0015_cgt_active_uq":
                row = connection.execute(
                    text(
                        """
                        SELECT 1
                        FROM pg_indexes
                        WHERE schemaname = 'public'
                          AND indexname = 'uq_cgt_active_contact_group'
                        """
                    ),
                ).fetchone()
                assert row is not None
            elif revision == "0016_messages_fts_ru":
                col = connection.execute(
                    text(
                        """
                        SELECT data_type, udt_name
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = 'messages'
                          AND column_name = 'search_vector'
                        """
                    ),
                ).fetchone()
                assert col is not None
                assert col[1] == "tsvector"
                idx = connection.execute(
                    text(
                        """
                        SELECT 1
                        FROM pg_indexes
                        WHERE schemaname = 'public'
                          AND indexname = 'idx_messages_search_vector'
                        """
                    ),
                ).fetchone()
                assert idx is not None
            elif revision == "0017_chat_read_state":
                row = connection.execute(
                    text(
                        """
                        SELECT 1
                        FROM information_schema.tables
                        WHERE table_schema = 'public'
                          AND table_name = 'chat_read_state'
                        """
                    ),
                ).fetchone()
                assert row is not None
                read_at = connection.execute(
                    text(
                        """
                        SELECT data_type
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = 'chat_read_state'
                          AND column_name = 'read_at'
                        """
                    ),
                ).fetchone()
                assert read_at is not None
                assert read_at[0] == "timestamp with time zone"
            elif revision == "0018_cgt_version":
                col = connection.execute(
                    text(
                        """
                        SELECT column_name, column_default
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = 'contact_group_transfers'
                          AND column_name = 'version'
                        """
                    ),
                ).fetchone()
                assert col is not None
    finally:
        engine.dispose()


def _assert_ownership_revision_dropped(alembic_config: Config, revision: str) -> None:
    engine = create_engine(_sync_database_url(alembic_config.get_main_option("sqlalchemy.url")))
    tables_by_revision = {
        "0012_contact_group_ownership": ("contact_group_assignments",),
        "0013_group_escalation_settings": ("group_escalation_settings",),
        "0014_message_reply_audit": ("message_reply_audit", "contact_group_transfers"),
        "0015_cgt_active_uq": (),
        "0016_messages_fts_ru": (),
        "0017_chat_read_state": ("chat_read_state",),
        "0018_cgt_version": (),
    }
    try:
        with engine.connect() as connection:
            for table in tables_by_revision[revision]:
                row = connection.execute(
                    text(
                        """
                        SELECT 1
                        FROM information_schema.tables
                        WHERE table_schema = 'public'
                          AND table_name = :table_name
                        """
                    ),
                    {"table_name": table},
                ).fetchone()
                assert row is None
            if revision == "0012_contact_group_ownership":
                col = connection.execute(
                    text(
                        """
                        SELECT column_name
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = 'chats'
                          AND column_name = 'assigned_user_id'
                        """
                    ),
                ).fetchone()
                assert col is not None
            if revision == "0015_cgt_active_uq":
                row = connection.execute(
                    text(
                        """
                        SELECT 1
                        FROM pg_indexes
                        WHERE schemaname = 'public'
                          AND indexname = 'uq_cgt_active_contact_group'
                        """
                    ),
                ).fetchone()
                assert row is None
            if revision == "0016_messages_fts_ru":
                col = connection.execute(
                    text(
                        """
                        SELECT column_name
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = 'messages'
                          AND column_name = 'search_vector'
                        """
                    ),
                ).fetchone()
                assert col is None
                idx = connection.execute(
                    text(
                        """
                        SELECT 1
                        FROM pg_indexes
                        WHERE schemaname = 'public'
                          AND indexname = 'idx_messages_search_vector'
                        """
                    ),
                ).fetchone()
                assert idx is None
            if revision == "0018_cgt_version":
                col = connection.execute(
                    text(
                        """
                        SELECT column_name
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = 'contact_group_transfers'
                          AND column_name = 'version'
                        """
                    ),
                ).fetchone()
                assert col is None
    finally:
        engine.dispose()
