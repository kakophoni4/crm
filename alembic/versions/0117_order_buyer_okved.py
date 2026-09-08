"""Store the buyer activity code on each application, never on its contact."""
from alembic import op
import sqlalchemy as sa

revision = "0117_order_buyer_okved"
down_revision = "0116_sync_lawyer_shops_to_accounting"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("lawyer_shops", sa.Column("received_at", sa.Date(), nullable=True))
    op.add_column("lead_opt_orders", sa.Column("buyer_okved", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("lawyer_shops", "received_at")
    op.drop_column("lead_opt_orders", "buyer_okved")
