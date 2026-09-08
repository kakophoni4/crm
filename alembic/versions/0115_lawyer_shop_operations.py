"""Operational fields for lawyer shops."""
from collections.abc import Sequence
from alembic import op
revision: str = "0115_lawyer_shop_operations"
down_revision: str | None = "0114_blacklist_entries"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None
def upgrade() -> None:
    op.execute("""ALTER TABLE lawyer_shops ADD COLUMN fns TEXT, ADD COLUMN sbis TEXT,
      ADD COLUMN edo_until DATE, ADD COLUMN edo_id TEXT, ADD COLUMN purchased_at DATE,
      ADD COLUMN failed_at DATE, ADD COLUMN failure_reason TEXT""")
def downgrade() -> None:
    op.execute("""ALTER TABLE lawyer_shops DROP COLUMN failure_reason, DROP COLUMN failed_at,
      DROP COLUMN purchased_at, DROP COLUMN edo_id, DROP COLUMN edo_until, DROP COLUMN sbis, DROP COLUMN fns""")
