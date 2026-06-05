"""Contact group assignments and backfill from chat assignee.

Revision ID: 0012_contact_group_ownership
Revises: 0011_bot_events_outbound
Create Date: 2026-05-17

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0012_contact_group_ownership"
down_revision: str | None = "0011_bot_events_outbound"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE contact_group_assignments (
            id BIGSERIAL PRIMARY KEY,
            contact_id BIGINT NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            group_id BIGINT NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
            owner_user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
            assigned_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            assignment_source TEXT NOT NULL,
            last_owner_response_at TIMESTAMPTZ,
            pending_inbound_at TIMESTAMPTZ,
            escalated_to_group_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_contact_group_assignments_contact_group
                UNIQUE (contact_id, group_id),
            CONSTRAINT chk_cga_assignment_source CHECK (
                assignment_source IN (
                    'auto_round_robin',
                    'auto_first_responder',
                    'auto_random_available',
                    'manual_transfer',
                    'senior_assign',
                    'migration'
                )
            )
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_cga_group_owner
        ON contact_group_assignments (group_id, owner_user_id)
        """
    )
    op.execute(
        "CREATE INDEX idx_cga_owner ON contact_group_assignments (owner_user_id)"
    )
    op.execute(
        """
        CREATE INDEX idx_cga_pending_inbound
        ON contact_group_assignments (pending_inbound_at)
        WHERE pending_inbound_at IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_contact_group_assignments_updated_at
        BEFORE UPDATE ON contact_group_assignments
        FOR EACH ROW
        EXECUTE FUNCTION update_timestamp_trigger()
        """
    )

    op.execute(
        """
        INSERT INTO contact_group_assignments (
            contact_id,
            group_id,
            owner_user_id,
            assigned_at,
            assignment_source
        )
        SELECT DISTINCT
            c.contact_id,
            b.owner_id,
            c.assigned_user_id,
            c.created_at,
            'migration'
        FROM chats c
        JOIN bots b ON b.id = c.bot_id AND b.owner_type = 'group'
        WHERE c.assigned_user_id IS NOT NULL
        ON CONFLICT (contact_id, group_id) DO UPDATE
        SET owner_user_id = EXCLUDED.owner_user_id
        WHERE contact_group_assignments.owner_user_id IS NULL
        """
    )

    op.execute(
        """
        COMMENT ON COLUMN chats.assigned_user_id IS
        'DEPRECATED as card owner — use contact_group_assignments.owner_user_id. '
        'Renamed to last_handled_by_user_id: last operator who wrote/opened, not ownership.'
        """
    )
    op.execute(
        "ALTER TABLE chats RENAME COLUMN assigned_user_id TO last_handled_by_user_id"
    )
    op.execute(
        """
        ALTER INDEX idx_chats_assigned_user_status
        RENAME TO idx_chats_last_handled_by_user_status
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN chats.last_handled_by_user_id IS
        'Last operator who wrote or opened the chat — NOT card owner. '
        'See contact_group_assignments.owner_user_id for ownership.'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER INDEX idx_chats_last_handled_by_user_status
        RENAME TO idx_chats_assigned_user_status
        """
    )
    op.execute(
        "ALTER TABLE chats RENAME COLUMN last_handled_by_user_id TO assigned_user_id"
    )
    op.execute("COMMENT ON COLUMN chats.assigned_user_id IS NULL")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_contact_group_assignments_updated_at "
        "ON contact_group_assignments"
    )
    op.execute("DROP TABLE IF EXISTS contact_group_assignments")
