"""Add storage-only nulevka role."""
from alembic import op

revision = "0122_nulevka_role"
down_revision = "0121_ai_integration"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'nulevka'")
    op.execute("ALTER TABLE users DROP CONSTRAINT ck_users_role_org")
    op.execute("""ALTER TABLE users ADD CONSTRAINT ck_users_role_org CHECK (
        (role IN ('user', 'group_senior') AND department_id IS NOT NULL)
        OR (role = 'senior' AND department_id IS NOT NULL AND group_id IS NULL)
        OR (role IN ('admin', 'accountant', 'chief_accountant', 'lawyer', 'kesher', 'nulevka')
            AND department_id IS NULL AND group_id IS NULL)
    )""")


def downgrade() -> None:
    # Refuse rollback while users of this role exist; never silently reassign them.
    op.execute("ALTER TABLE users DROP CONSTRAINT ck_users_role_org")
    op.execute("""ALTER TABLE users ADD CONSTRAINT ck_users_role_org CHECK (
        (role IN ('user', 'group_senior') AND department_id IS NOT NULL)
        OR (role = 'senior' AND department_id IS NOT NULL AND group_id IS NULL)
        OR (role IN ('admin', 'accountant', 'chief_accountant', 'lawyer', 'kesher')
            AND department_id IS NULL AND group_id IS NULL)
    )""")
