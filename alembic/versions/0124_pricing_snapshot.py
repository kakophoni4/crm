"""Persist line pricing for new calculations without repricing existing orders."""
from alembic import op
revision = '0124_pricing_snapshot'
down_revision = '0123_sales_seasons'
branch_labels = None
depends_on = None

def upgrade():
    op.execute("ALTER TABLE lead_opt_order_lines ADD COLUMN pricing_rate_percent NUMERIC(8,4), ADD COLUMN pricing_category TEXT")

def downgrade():
    op.execute('ALTER TABLE lead_opt_order_lines DROP COLUMN pricing_rate_percent, DROP COLUMN pricing_category')
