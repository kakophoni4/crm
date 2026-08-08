"""Backfill orphan contact owners from contacts.created_by (manual creates).

Revision ID: 0097_backfill_contact_owners
Revises: 0096_opt_sales_book_extracts

Only contacts with audit_log contact.create (skips bot upsert orphans).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0097_backfill_contact_owners"
down_revision: str | None = "0096_opt_sales_book_extracts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1) Fill NULL owners on existing assignments for manually created contacts.
    op.execute(
        """
        UPDATE contact_group_assignments AS cga
        SET
            owner_user_id = c.created_by,
            assignment_source = CASE
                WHEN cga.assignment_source IS NULL OR btrim(cga.assignment_source) = ''
                THEN 'manual_create_backfill'
                ELSE cga.assignment_source
            END,
            updated_at = now()
        FROM contacts AS c
        WHERE cga.contact_id = c.id
          AND cga.owner_user_id IS NULL
          AND c.created_by IS NOT NULL
          AND EXISTS (
              SELECT 1
              FROM audit_log AS a
              WHERE a.entity_type = 'contact'
                AND a.entity_id = c.id
                AND a.action::text = 'contact.create'
          )
        """
    )

    # 2) Insert missing CGA for manually created contacts without any assignment.
    #    Prefer creator's primary group, then membership, then department group.
    op.execute(
        """
        INSERT INTO contact_group_assignments (
            contact_id,
            group_id,
            owner_user_id,
            assigned_at,
            assignment_source
        )
        SELECT
            c.id,
            COALESCE(
                u.group_id,
                (
                    SELECT ugm.group_id
                    FROM user_group_memberships AS ugm
                    WHERE ugm.user_id = c.created_by
                    ORDER BY ugm.group_id
                    LIMIT 1
                ),
                (
                    SELECT g.id
                    FROM groups AS g
                    WHERE g.department_id = COALESCE(c.assigned_department_id, u.department_id)
                      AND g.name <> '__department_inbox__'
                    ORDER BY g.id
                    LIMIT 1
                )
            ) AS group_id,
            c.created_by,
            COALESCE(c.created_at, now()),
            'manual_create_backfill'
        FROM contacts AS c
        JOIN users AS u ON u.id = c.created_by
        WHERE c.created_by IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM contact_group_assignments AS cga
              WHERE cga.contact_id = c.id
          )
          AND EXISTS (
              SELECT 1
              FROM audit_log AS a
              WHERE a.entity_type = 'contact'
                AND a.entity_id = c.id
                AND a.action::text = 'contact.create'
          )
          AND COALESCE(
                u.group_id,
                (
                    SELECT ugm.group_id
                    FROM user_group_memberships AS ugm
                    WHERE ugm.user_id = c.created_by
                    ORDER BY ugm.group_id
                    LIMIT 1
                ),
                (
                    SELECT g.id
                    FROM groups AS g
                    WHERE g.department_id = COALESCE(c.assigned_department_id, u.department_id)
                      AND g.name <> '__department_inbox__'
                    ORDER BY g.id
                    LIMIT 1
                )
            ) IS NOT NULL
        ON CONFLICT (contact_id, group_id) DO UPDATE
        SET
            owner_user_id = COALESCE(
                contact_group_assignments.owner_user_id,
                EXCLUDED.owner_user_id
            ),
            updated_at = now()
        """
    )


def downgrade() -> None:
    # Non-destructive: leave backfilled ownership in place.
    pass
