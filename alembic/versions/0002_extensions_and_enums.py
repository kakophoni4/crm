"""Extensions and PostgreSQL enum types.

Revision ID: 0002_extensions_and_enums
Revises: 0001_initial
Create Date: 2026-05-16

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002_extensions_and_enums"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ENUMS: list[tuple[str, list[str]]] = [
    ("user_role", ["user", "senior", "admin"]),
    ("chat_status", ["open", "closed", "archived"]),
    (
        "transfer_status",
        [
            "pending_senior",
            "pending_recipient",
            "accepted",
            "declined_senior",
            "declined_recipient",
            "cancelled",
            "expired",
        ],
    ),
    ("message_direction", ["in", "out"]),
    ("message_kind", ["text", "attachment", "system"]),
    ("contact_status", ["active", "disabled", "merged"]),
    ("bot_owner_type", ["department", "group"]),
    ("bot_outbound_status", ["queued", "sent", "failed"]),
    (
        "audit_action",
        [
            "user.create",
            "user.update",
            "user.delete",
            "auth.login",
            "auth.logout",
            "auth.force_logout",
            "department.create",
            "department.update",
            "department.delete",
            "group.create",
            "group.update",
            "group.delete",
            "chat.transfer.request",
            "chat.transfer.approve",
            "chat.transfer.decline",
            "chat.takeover",
            "contact.create",
            "contact.update",
            "bot.create",
            "bot.update",
        ],
    ),
]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")

    for name, values in _ENUMS:
        quoted = ", ".join(f"'{v}'" for v in values)
        op.execute(f"CREATE TYPE {name} AS ENUM ({quoted})")


def downgrade() -> None:
    for name, _ in reversed(_ENUMS):
        op.execute(f"DROP TYPE IF EXISTS {name}")

    op.execute("DROP EXTENSION IF EXISTS citext")
    op.execute("DROP EXTENSION IF EXISTS pgcrypto")
