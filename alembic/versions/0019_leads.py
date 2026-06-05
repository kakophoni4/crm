"""Leads table, statuses.kind, chat/message lead FKs, backfill.

Revision ID: 0019_leads
Revises: 0018_cgt_version
Create Date: 2026-05-17

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0019_leads"
down_revision: str | None = "0018_cgt_version"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CHAT_LABEL_SEED: list[tuple[str, str, str, int]] = [
    ("client_new", "Новый клиент", "#6B7280", 0),
    ("client_returning", "Постоянный клиент", "#3B82F6", 10),
]


def upgrade() -> None:
    op.add_column(
        "statuses",
        sa.Column(
            "kind",
            sa.Text(),
            nullable=False,
            server_default="lead_pipeline",
        ),
    )
    op.execute(
        """
        ALTER TABLE statuses
        ADD CONSTRAINT chk_statuses_kind
        CHECK (kind IN ('chat_label', 'lead_pipeline'))
        """
    )
    op.drop_constraint("statuses_code_key", "statuses", type_="unique")
    op.create_index("uq_statuses_code_kind", "statuses", ["code", "kind"], unique=True)
    op.execute(
        """
        CREATE INDEX idx_statuses_kind_active
        ON statuses (kind, sort_order)
        WHERE is_active
        """
    )

    for code, label, color, sort_order in _CHAT_LABEL_SEED:
        op.execute(
            sa.text(
                """
                INSERT INTO statuses (code, kind, label, color, sort_order)
                VALUES (:code, 'chat_label', :label, :color, :sort_order)
                """
            ).bindparams(code=code, label=label, color=color, sort_order=sort_order)
        )

    op.create_table(
        "leads",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("contact_id", sa.BigInteger(), nullable=False),
        sa.Column("group_id", sa.BigInteger(), nullable=False),
        sa.Column("bot_id", sa.BigInteger(), nullable=True),
        sa.Column("chat_id", sa.BigInteger(), nullable=True),
        sa.Column("status_id", sa.BigInteger(), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retention_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column(
            "custom_fields",
            sa.dialects.postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["bot_id"], ["bots.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["chat_id"], ["chats.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["status_id"], ["statuses.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_leads_open_contact_group
        ON leads (contact_id, group_id)
        WHERE closed_at IS NULL
        """
    )
    op.create_index("idx_leads_contact_closed", "leads", ["contact_id", "closed_at"])
    op.execute(
        """
        CREATE INDEX idx_leads_group_created
        ON leads (group_id, created_at DESC)
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_leads_updated_at
        BEFORE UPDATE ON leads
        FOR EACH ROW
        EXECUTE FUNCTION update_timestamp_trigger()
        """
    )

    op.add_column("messages", sa.Column("lead_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "fk_messages_lead_id",
        "messages",
        "leads",
        ["lead_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.execute(
        """
        CREATE INDEX idx_messages_lead_created
        ON messages (lead_id, created_at)
        """
    )

    op.add_column("chats", sa.Column("current_lead_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "fk_chats_current_lead_id",
        "chats",
        "leads",
        ["current_lead_id"],
        ["id"],
        ondelete="SET NULL",
    )

    _backfill_open_leads()


def _backfill_open_leads() -> None:
    op.execute(
        """
        INSERT INTO leads (
            contact_id,
            group_id,
            bot_id,
            chat_id,
            status_id,
            created_at,
            updated_at
        )
        SELECT
            c.contact_id,
            c.assigned_group_id,
            c.bot_id,
            c.id,
            (
                SELECT s.id
                FROM statuses s
                WHERE s.code = 'new' AND s.kind = 'lead_pipeline'
                LIMIT 1
            ),
            COALESCE(c.last_message_at, c.created_at),
            COALESCE(c.last_message_at, c.created_at)
        FROM chats c
        WHERE c.assigned_group_id IS NOT NULL
          AND c.status::text != 'archived'
          AND NOT EXISTS (
              SELECT 1
              FROM leads l
              WHERE l.contact_id = c.contact_id
                AND l.group_id = c.assigned_group_id
                AND l.closed_at IS NULL
          )
        """
    )
    op.execute(
        """
        UPDATE chats c
        SET current_lead_id = sub.lead_id
        FROM (
            SELECT
                c2.id AS chat_id,
                (
                    SELECT l.id
                    FROM leads l
                    WHERE l.contact_id = c2.contact_id
                      AND l.group_id = c2.assigned_group_id
                      AND l.closed_at IS NULL
                    ORDER BY l.id DESC
                    LIMIT 1
                ) AS lead_id
            FROM chats c2
            WHERE c2.assigned_group_id IS NOT NULL
              AND c2.status::text != 'archived'
        ) sub
        WHERE c.id = sub.chat_id
          AND sub.lead_id IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE messages m
        SET lead_id = c.current_lead_id
        FROM chats c
        WHERE m.chat_id = c.id
          AND m.lead_id IS NULL
          AND c.current_lead_id IS NOT NULL
        """
    )


def _dedupe_statuses_for_legacy_unique_code() -> None:
    op.execute(
        """
        WITH ranked AS (
            SELECT
                s.id,
                s.code,
                FIRST_VALUE(s.id) OVER (
                    PARTITION BY s.code
                    ORDER BY
                        CASE WHEN s.kind = 'lead_pipeline' THEN 0 ELSE 1 END,
                        s.id
                ) AS keep_id,
                ROW_NUMBER() OVER (
                    PARTITION BY s.code
                    ORDER BY
                        CASE WHEN s.kind = 'lead_pipeline' THEN 0 ELSE 1 END,
                        s.id
                ) AS rn
            FROM statuses s
        ),
        duplicates AS (
            SELECT id, keep_id
            FROM ranked
            WHERE rn > 1
        )
        UPDATE chats c
        SET status_id = d.keep_id
        FROM duplicates d
        WHERE c.status_id = d.id
        """
    )
    op.execute(
        """
        WITH ranked AS (
            SELECT
                s.id,
                ROW_NUMBER() OVER (
                    PARTITION BY s.code
                    ORDER BY
                        CASE WHEN s.kind = 'lead_pipeline' THEN 0 ELSE 1 END,
                        s.id
                ) AS rn
            FROM statuses s
        )
        DELETE FROM statuses s
        USING ranked r
        WHERE s.id = r.id
          AND r.rn > 1
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE messages m
        SET lead_id = NULL
        FROM chats c
        WHERE m.chat_id = c.id AND m.lead_id IS NOT NULL
        """
    )
    op.drop_constraint("fk_chats_current_lead_id", "chats", type_="foreignkey")
    op.drop_column("chats", "current_lead_id")

    op.drop_constraint("fk_messages_lead_id", "messages", type_="foreignkey")
    op.execute("DROP INDEX IF EXISTS idx_messages_lead_created")
    op.drop_column("messages", "lead_id")

    op.execute("DROP TRIGGER IF EXISTS trg_leads_updated_at ON leads")
    op.drop_table("leads")

    for code, _, _, _ in _CHAT_LABEL_SEED:
        op.execute(
            sa.text("DELETE FROM statuses WHERE code = :code AND kind = 'chat_label'").bindparams(
                code=code
            )
        )

    op.execute("DROP INDEX IF EXISTS idx_statuses_kind_active")
    op.drop_index("uq_statuses_code_kind", table_name="statuses")
    _dedupe_statuses_for_legacy_unique_code()
    op.create_unique_constraint("statuses_code_key", "statuses", ["code"])
    op.execute("ALTER TABLE statuses DROP CONSTRAINT IF EXISTS chk_statuses_kind")
    op.drop_column("statuses", "kind")
