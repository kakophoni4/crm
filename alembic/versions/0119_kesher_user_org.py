"""Allow kesher users without a group or department."""
from alembic import op

revision = "0119_kesher_user_org"
down_revision = "0118_cashroom"
branch_labels = None
depends_on = None


def replace_constraint(include_kesher: bool) -> None:
    extra = "OR (role = 'kesher' AND department_id IS NULL AND group_id IS NULL)" if include_kesher else ""
    op.execute("ALTER TABLE users DROP CONSTRAINT ck_users_role_org")
    op.execute(f"""
        ALTER TABLE users ADD CONSTRAINT ck_users_role_org CHECK (
            (role = 'user' AND department_id IS NOT NULL)
            OR (role = 'group_senior' AND department_id IS NOT NULL)
            OR (role = 'senior' AND department_id IS NOT NULL AND group_id IS NULL)
            OR (role = 'admin' AND department_id IS NULL AND group_id IS NULL)
            OR (role = 'accountant' AND department_id IS NULL AND group_id IS NULL)
            OR (role = 'chief_accountant' AND department_id IS NULL AND group_id IS NULL)
            OR (role = 'lawyer' AND department_id IS NULL AND group_id IS NULL)
            {extra}
        )
    """)


def upgrade() -> None:
    replace_constraint(True)


def downgrade() -> None:
    # Refuse the rollback if kesher users exist; never delete or reassign them.
    replace_constraint(False)
