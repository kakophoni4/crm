"""AI integration state and personal audit."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0121_ai_integration"
down_revision = "0120_shop_access_contacts"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ai_requests",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("actor_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), sa.ForeignKey("chats.id", ondelete="CASCADE")),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("body", postgresql.JSONB(), nullable=False),
        sa.Column("meta", postgresql.JSONB(), nullable=False),
        sa.Column("result", postgresql.JSONB()),
        sa.Column("error", postgresql.JSONB()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_ai_requests_status", "ai_requests", ["status"])
    op.create_table(
        "ai_chat_state",
        sa.Column(
            "chat_id",
            sa.BigInteger(),
            sa.ForeignKey("chats.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("data", postgresql.JSONB(), nullable=False),
        sa.Column("updated_by", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
    )
    op.create_table(
        "ai_audit",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("actor_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("data", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.execute("""
    CREATE FUNCTION crm_ai_message_changed() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF NEW.kind::text = 'system' THEN RETURN NEW; END IF;
      IF NEW.direction::text = 'inbound' THEN
        UPDATE ai_chat_state SET revision=revision+1,
          data=data || jsonb_build_object('last_inbound_id',NEW.id,
            'first_unanswered_at',
          COALESCE(data->>'first_unanswered_at',
          to_char(NOW() AT TIME ZONE 'UTC',
          'YYYY-MM-DD"T"HH24:MI:SS.US')||'+00:00'),

            'pending_request_id',NULL)
          WHERE chat_id=NEW.chat_id AND mode <> 'OFF';
      ELSIF NEW.sender_user_id IS NOT NULL THEN
        UPDATE ai_chat_state SET revision=revision+1,
           mode=CASE WHEN mode='ASSISTANT' THEN 'MANAGER' ELSE mode END,

          data=data || jsonb_build_object('first_unanswered_at',
          NULL,
          'pending_request_id',
          NULL,
          'fallback_done',
          false,
          'fallback_failed',
          false,
          'notified',
          false,
          'error',
          NULL)
          WHERE chat_id=NEW.chat_id;
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER crm_ai_message_changed
      AFTER INSERT ON messages FOR EACH ROW EXECUTE FUNCTION crm_ai_message_changed();
    CREATE FUNCTION crm_ai_chat_changed() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF OLD.status IS DISTINCT FROM NEW.status
        OR OLD.assigned_group_id IS DISTINCT FROM NEW.assigned_group_id
        OR OLD.assigned_department_id IS DISTINCT FROM NEW.assigned_department_id THEN
        UPDATE ai_chat_state SET revision=revision+1,
           data=data || jsonb_build_object('pending_request_id',
          NULL)
        WHERE chat_id=NEW.id;
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER crm_ai_chat_changed
      AFTER UPDATE ON chats FOR EACH ROW EXECUTE FUNCTION crm_ai_chat_changed();
    """)


def downgrade():
    op.execute("DROP TRIGGER crm_ai_chat_changed ON chats")
    op.execute("DROP FUNCTION crm_ai_chat_changed()")
    op.execute("DROP TRIGGER crm_ai_message_changed ON messages")
    op.execute("DROP FUNCTION crm_ai_message_changed()")
    op.drop_table("ai_audit")
    op.drop_table("ai_chat_state")
    op.drop_table("ai_requests")
