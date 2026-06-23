"""Quick reply templates.

Revision ID: 0049_quick_reply_templates
Revises: 0048_telephony_calls
"""

from __future__ import annotations

from alembic import op

revision = "0049_quick_reply_templates"
down_revision = "0048_telephony_calls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE quick_reply_templates (
            id BIGSERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            department_id BIGINT NULL REFERENCES departments(id) ON DELETE CASCADE,
            group_id BIGINT NULL REFERENCES groups(id) ON DELETE CASCADE,
            is_active BOOLEAN NOT NULL DEFAULT true,
            usage_count INTEGER NOT NULL DEFAULT 0,
            created_by BIGINT NULL REFERENCES users(id) ON DELETE SET NULL,
            updated_by BIGINT NULL REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_quick_reply_scope
                CHECK (department_id IS NOT NULL OR group_id IS NOT NULL)
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_quick_reply_templates_department "
        "ON quick_reply_templates (department_id)"
    )
    op.execute(
        "CREATE INDEX idx_quick_reply_templates_group "
        "ON quick_reply_templates (group_id)"
    )
    op.execute(
        "CREATE INDEX idx_quick_reply_templates_active "
        "ON quick_reply_templates (is_active)"
    )
    op.execute(
        """
        CREATE TRIGGER trg_quick_reply_templates_updated_at
        BEFORE UPDATE ON quick_reply_templates
        FOR EACH ROW EXECUTE FUNCTION update_timestamp_trigger()
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_quick_reply_templates_updated_at "
        "ON quick_reply_templates"
    )
    op.execute("DROP TABLE IF EXISTS quick_reply_templates")
