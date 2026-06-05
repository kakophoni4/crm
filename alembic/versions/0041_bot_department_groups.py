"""Bot department ownership and senior group assignments.

Revision ID: 0041_bot_department_groups
Revises: 0040_uploaded_files
"""

from __future__ import annotations

from alembic import op

revision = "0041_bot_department_groups"
down_revision = "0040_uploaded_files"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE bots ADD COLUMN department_id BIGINT")
    op.execute(
        """
        UPDATE bots
        SET department_id = owner_id
        WHERE owner_type = 'department'
        """
    )
    op.execute(
        """
        UPDATE bots b
        SET department_id = g.department_id
        FROM groups g
        WHERE b.owner_type = 'group' AND b.owner_id = g.id
        """
    )
    op.execute(
        """
        UPDATE bots
        SET department_id = owner_id
        WHERE department_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE bots b
        SET department_id = sub.id
        FROM (SELECT id FROM departments ORDER BY id ASC LIMIT 1) sub
        WHERE b.department_id IS NULL
           OR NOT EXISTS (
               SELECT 1 FROM departments d WHERE d.id = b.department_id
           )
        """
    )
    op.execute(
        """
        ALTER TABLE bots
        ALTER COLUMN department_id SET NOT NULL
        """
    )
    op.execute(
        """
        ALTER TABLE bots
        ADD CONSTRAINT fk_bots_department_id
        FOREIGN KEY (department_id) REFERENCES departments(id)
        """
    )
    op.execute("CREATE INDEX idx_bots_department_id ON bots (department_id)")
    op.execute(
        """
        CREATE TABLE bot_group_assignments (
            bot_id BIGINT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
            group_id BIGINT NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (bot_id, group_id)
        )
        """
    )
    op.execute("CREATE INDEX idx_bot_group_assignments_group_id ON bot_group_assignments (group_id)")
    op.execute(
        """
        INSERT INTO bot_group_assignments (bot_id, group_id)
        SELECT id, owner_id FROM bots WHERE owner_type = 'group'
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS bot_group_assignments")
    op.execute("ALTER TABLE bots DROP CONSTRAINT IF EXISTS fk_bots_department_id")
    op.execute("DROP INDEX IF EXISTS idx_bots_department_id")
    op.execute("ALTER TABLE bots DROP COLUMN IF EXISTS department_id")
