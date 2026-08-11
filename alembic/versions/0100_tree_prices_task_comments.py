"""Tree service prices + department task comments.

Revision ID: 0100_tree_prices_task_comments
Revises: 0099_vault_folders
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0100_tree_prices_task_comments"
down_revision: str | None = "0099_vault_folders"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SEED = [
    ("archive_extract", "Архивная выписка"),
    ("book", "Книга"),
    ("tree", "Дерево"),
    ("base", "База"),
    ("sur", "СУР"),
    ("other", "Другое"),
    ("deposit", "Депозит"),
]


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tree_service_prices (
            type_code VARCHAR(64) PRIMARY KEY,
            label TEXT NOT NULL,
            unit_price NUMERIC(14, 2) NULL,
            is_active BOOLEAN NOT NULL DEFAULT true,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    for code, label in _SEED:
        op.execute(
            f"""
            INSERT INTO tree_service_prices (type_code, label, unit_price, is_active)
            VALUES ('{code}', '{label}', NULL, true)
            ON CONFLICT (type_code) DO NOTHING
            """
        )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS department_task_comments (
            id BIGSERIAL PRIMARY KEY,
            task_id BIGINT NOT NULL REFERENCES department_tasks(id) ON DELETE CASCADE,
            author_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            body TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_department_task_comments_task_id
            ON department_task_comments (task_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_department_task_comments_author_id
            ON department_task_comments (author_id)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS department_task_comments")
    op.execute("DROP TABLE IF EXISTS tree_service_prices")
