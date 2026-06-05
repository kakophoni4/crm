"""Contacts, field-level audit, and global audit_log.

Revision ID: 0005_contacts_and_audit
Revises: 0004_seed_admin
Create Date: 2026-05-16

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0005_contacts_and_audit"
down_revision: str | None = "0004_seed_admin"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # New enum labels must be committed before use in DDL (PostgreSQL).
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE contact_status ADD VALUE IF NOT EXISTS 'new'")
        op.execute("ALTER TYPE contact_status ADD VALUE IF NOT EXISTS 'archived'")
        op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'contact.delete'")

    op.execute(
        """
        CREATE TABLE contacts (
            id BIGSERIAL PRIMARY KEY,
            telegram_user_id BIGINT UNIQUE,
            telegram_username CITEXT,
            full_name TEXT NOT NULL,
            phone TEXT,
            email CITEXT,
            status contact_status NOT NULL DEFAULT 'new',
            custom_fields JSONB NOT NULL DEFAULT '{}'::jsonb,
            assigned_user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
            assigned_group_id BIGINT REFERENCES groups(id) ON DELETE SET NULL,
            assigned_department_id BIGINT REFERENCES departments(id) ON DELETE SET NULL,
            source TEXT,
            archived_at TIMESTAMPTZ,
            created_by BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX idx_contacts_telegram_user_id ON contacts (telegram_user_id)")
    op.execute("CREATE INDEX idx_contacts_telegram_username ON contacts (telegram_username)")
    op.execute("CREATE INDEX idx_contacts_assigned_user_id ON contacts (assigned_user_id)")
    op.execute("CREATE INDEX idx_contacts_assigned_group_id ON contacts (assigned_group_id)")
    op.execute(
        "CREATE INDEX idx_contacts_assigned_department_id ON contacts (assigned_department_id)"
    )
    op.execute("CREATE INDEX idx_contacts_status ON contacts (status)")
    op.execute("CREATE INDEX idx_contacts_custom_fields ON contacts USING GIN (custom_fields)")

    op.execute(
        """
        CREATE TRIGGER trg_contacts_updated_at
        BEFORE UPDATE ON contacts
        FOR EACH ROW
        EXECUTE FUNCTION update_timestamp_trigger()
        """
    )

    op.execute(
        """
        CREATE TABLE contact_field_changes (
            id BIGSERIAL PRIMARY KEY,
            contact_id BIGINT NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            field_name TEXT NOT NULL,
            old_value JSONB,
            new_value JSONB,
            changed_by BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            changed_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_cfc_contact_changed_at
        ON contact_field_changes (contact_id, changed_at DESC)
        """
    )

    op.execute(
        """
        CREATE TABLE audit_log (
            id BIGSERIAL PRIMARY KEY,
            actor_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
            action audit_action NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id BIGINT NOT NULL,
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            ip INET,
            user_agent TEXT,
            request_id TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX idx_audit_log_actor_id ON audit_log (actor_id)")
    op.execute("CREATE INDEX idx_audit_log_entity ON audit_log (entity_type, entity_id)")
    op.execute("CREATE INDEX idx_audit_log_created_at ON audit_log (created_at DESC)")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_contacts_updated_at ON contacts")
    op.execute("DROP TABLE IF EXISTS audit_log")
    op.execute("DROP TABLE IF EXISTS contact_field_changes")
    op.execute("DROP TABLE IF EXISTS contacts")
