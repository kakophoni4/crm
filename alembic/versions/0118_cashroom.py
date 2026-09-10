"""Cashroom deals, cash ledger and restricted kesher role."""
from alembic import op
import sqlalchemy as sa
revision = "0118_cashroom"
down_revision = "0117_order_buyer_okved"
branch_labels = None
depends_on = None


def upgrade():
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'kesher'")
    op.create_table("cash_accounts", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("name", sa.String(100), nullable=False, unique=True))
    op.create_table("cash_deals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("entered_on", sa.Date(), nullable=False), sa.Column("due_on", sa.Date()),
        *(sa.Column(k, sa.String(200), nullable=False) for k in ("payer", "receiver", "client", "executor", "manager")),
        sa.Column("payer_inn", sa.String(12), nullable=False), sa.Column("receiver_inn", sa.String(12), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        *(sa.Column(k, sa.Numeric(6, 3), nullable=False) for k in ("executor_rate", "client_rate", "manager_rate")),
        sa.Column("comment", sa.Text(), nullable=False), sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("amount > 0", name="positive_amount"),
        *(sa.CheckConstraint(f"{k} >= 0 AND {k} <= 100", name=f"{k}_range") for k in ("executor_rate", "client_rate", "manager_rate")),
    )
    for k in ("entered_on", "client", "executor"):
        op.create_index(f"ix_cash_deals_{k}", "cash_deals", [k])
    op.create_table("cash_movements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("operation_key", sa.String(36), nullable=False, unique=True),
        sa.Column("deal_id", sa.Integer(), sa.ForeignKey("cash_deals.id")),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("cash_accounts.id"), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False), sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("occurred_on", sa.Date(), nullable=False),
        *(sa.Column(k, sa.String(200), nullable=False) for k in ("client", "manager")),
        sa.Column("comment", sa.Text(), nullable=False), sa.Column("comment2", sa.Text(), nullable=False),
        sa.Column("voided", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_by", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False), sa.CheckConstraint("amount > 0", name="positive_amount"),
    )
    for k in ("deal_id", "account_id", "occurred_on"):
        op.create_index(f"ix_cash_movements_{k}", "cash_movements", [k])
    op.create_table("cash_audit",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("deal_id", sa.Integer(), sa.ForeignKey("cash_deals.id")),
        sa.Column("movement_id", sa.Integer(), sa.ForeignKey("cash_movements.id")),
        sa.Column("actor_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("action", sa.String(40), nullable=False), sa.Column("changes", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_cash_audit_deal_id", "cash_audit", ["deal_id"])


def downgrade():
    for name in ("cash_audit", "cash_movements", "cash_deals", "cash_accounts"):
        op.drop_table(name)
    # PostgreSQL enum values cannot safely be removed while users may hold the role.
