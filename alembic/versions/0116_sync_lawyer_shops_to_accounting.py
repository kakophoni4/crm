"""Expose existing lawyer shops in accounting assignments.

Revision ID: 0116_sync_lawyer_shops_to_accounting
Revises: 0115_lawyer_shop_operations
"""

from alembic import op


revision = "0116_sync_lawyer_shops_to_accounting"
down_revision = "0115_lawyer_shop_operations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Imported legal shops start in the "requirements" pool. A chief accountant
    # explicitly moves a shop to sales when it is ready to receive applications.
    op.execute("""
        INSERT INTO opt_units (inn, name, category_code, is_active)
        SELECT inn, name, 'TECH', false
        FROM lawyer_shops
        WHERE hidden_at IS NULL
        ON CONFLICT (inn) DO UPDATE
        SET name = EXCLUDED.name,
            updated_at = now()
    """)


def downgrade() -> None:
    # Do not remove units: they may already have accountant assignments or orders.
    pass
