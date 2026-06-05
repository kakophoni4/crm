"""Statuses reference table and seed data.

Revision ID: 0007_statuses
Revises: 0005_contacts_and_audit
Create Date: 2026-05-16

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0007_statuses"
down_revision: str | None = "0005_contacts_and_audit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SEED_STATUSES: list[tuple[str, str, str, int]] = [
    ("new", "Новый", "#6B7280", 0),
    ("in_progress", "В работе", "#FFB020", 10),
    ("qualified", "Квалифицирован", "#3B82F6", 20),
    ("won", "Выигран", "#22C55E", 30),
    ("lost", "Проигран", "#EF4444", 40),
]


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE statuses (
            id BIGSERIAL PRIMARY KEY,
            code TEXT NOT NULL UNIQUE,
            label TEXT NOT NULL,
            color VARCHAR(7),
            sort_order INT NOT NULL DEFAULT 0,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX idx_statuses_is_active ON statuses (is_active)")
    op.execute("CREATE INDEX idx_statuses_sort_order ON statuses (sort_order)")

    op.execute(
        """
        CREATE TRIGGER trg_statuses_updated_at
        BEFORE UPDATE ON statuses
        FOR EACH ROW
        EXECUTE FUNCTION update_timestamp_trigger()
        """
    )

    for code, label, color, sort_order in _SEED_STATUSES:
        op.execute(
            f"""
            INSERT INTO statuses (code, label, color, sort_order)
            VALUES ('{code}', '{label}', '{color}', {sort_order})
            """
        )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_statuses_updated_at ON statuses")
    op.execute("DROP TABLE IF EXISTS statuses")
