"""Blacklist for OPT application uploads."""
from collections.abc import Sequence
from alembic import op

revision: str = "0114_blacklist_entries"
down_revision: str | None = "0113_opt_payment_register"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""CREATE TABLE blacklist_entries (
      id BIGSERIAL PRIMARY KEY, kind TEXT NOT NULL, value TEXT NOT NULL, reason TEXT NOT NULL,
      created_by BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      CONSTRAINT uq_blacklist_entries_kind_value UNIQUE (kind, value)
    )""")


def downgrade() -> None:
    op.execute("DROP TABLE blacklist_entries")
