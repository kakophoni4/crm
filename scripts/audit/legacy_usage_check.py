#!/usr/bin/env python3
"""Pre-phase-2 audit: legacy chat_transfers rows and last legacy transfer activity.

Usage:
    python scripts/audit/legacy_usage_check.py
    DATABASE_URL=postgresql://... python scripts/audit/legacy_usage_check.py

Exit 0 when checks complete; prints JSON-ish summary to stdout.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _sync_url(database_url: str) -> str:
    for prefix in ("postgresql+asyncpg://", "postgresql+psycopg2://", "postgresql://"):
        if database_url.startswith(prefix):
            return "postgresql+psycopg://" + database_url.removeprefix(prefix)
    return database_url


def main() -> int:
    database_url = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://crm:crm@localhost:5433/crm",
    )
    engine = create_engine(_sync_url(database_url))
    legacy_transfer_actions = (
        "chat.transfer.request",
        "chat.transfer.approve",
        "chat.transfer.accept",
        "chat.transfer.decline",
        "chat.transfer.cancel",
        "chat.transfer.force",
    )

    try:
        with engine.connect() as conn:
            table_row = conn.execute(
                text(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name IN ('chat_transfers', 'chat_transfers_archived_2026')
                    ORDER BY table_name
                    """
                ),
            ).fetchall()
            tables = [r[0] for r in table_row]
            transfer_table = (
                "chat_transfers_archived_2026"
                if "chat_transfers_archived_2026" in tables
                else ("chat_transfers" if "chat_transfers" in tables else None)
            )

            row_count = None
            max_updated_at = None
            if transfer_table:
                row_count = conn.execute(
                    text(f"SELECT COUNT(*) FROM {transfer_table}"),
                ).scalar_one()
                max_updated_at = conn.execute(
                    text(f"SELECT MAX(created_at) FROM {transfer_table}"),
                ).scalar_one()

            legacy_audit = conn.execute(
                text(
                    """
                    SELECT MAX(created_at)
                    FROM audit_log
                    WHERE entity_type = 'chat_transfer'
                       OR action::text = ANY(:actions)
                    """
                ),
                {"actions": list(legacy_transfer_actions)},
            ).scalar_one()

            unread_col = conn.execute(
                text(
                    """
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'chats'
                      AND column_name = 'unread_count_user'
                    """
                ),
            ).fetchone()

            contact_legacy_cols = conn.execute(
                text(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'contacts'
                      AND column_name IN ('assigned_user_id', 'assigned_group_id')
                    ORDER BY column_name
                    """
                ),
            ).fetchall()
    finally:
        engine.dispose()

    print("=== Legacy ownership phase-2 audit ===")
    print(f"transfer_table: {transfer_table!r}")
    print(f"chat_transfers_count: {row_count}")
    print(f"chat_transfers_max_updated_at: {max_updated_at}")
    print(f"audit_log_legacy_transfer_max_created_at: {legacy_audit}")
    print(f"chats.unread_count_user_present: {unread_col is not None}")
    print(f"contacts_legacy_columns: {[r[0] for r in contact_legacy_cols]}")
    print()
    print(
        "Prod checklist: LEGACY_CHAT_TRANSFERS_ENABLED must not be 'true' "
        "(grep deploy/.env* and runtime env)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
