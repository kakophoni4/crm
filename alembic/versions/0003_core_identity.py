"""Core identity: org structure, users, sessions, refresh tokens.

Revision ID: 0003_core_identity
Revises: 0002_extensions_and_enums
Create Date: 2026-05-16

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003_core_identity"
down_revision: str | None = "0002_extensions_and_enums"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TIMESTAMP_TRIGGER = """
CREATE OR REPLACE FUNCTION update_timestamp_trigger()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

_TABLES_WITH_TIMESTAMPS = (
    "departments",
    "groups",
    "users",
    "user_sessions",
    "refresh_tokens",
)

_USER_ENUMS: list[tuple[str, list[str]]] = [
    ("user_status", ["active", "disabled"]),
    ("user_presence", ["online", "away", "busy", "offline"]),
    ("user_availability", ["available", "do_not_assign"]),
]


def upgrade() -> None:
    for name, values in _USER_ENUMS:
        quoted = ", ".join(f"'{v}'" for v in values)
        op.execute(f"CREATE TYPE {name} AS ENUM ({quoted})")

    op.execute(_TIMESTAMP_TRIGGER)

    op.execute(
        """
        CREATE TABLE departments (
            id BIGSERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            head_user_id BIGINT,
            created_by BIGINT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_departments_name UNIQUE (name)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE groups (
            id BIGSERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            department_id BIGINT NOT NULL REFERENCES departments(id) ON DELETE RESTRICT,
            created_by BIGINT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_groups_department_name UNIQUE (department_id, name)
        )
        """
    )
    op.execute("CREATE INDEX idx_groups_department ON groups (department_id)")

    op.execute(
        """
        CREATE TABLE users (
            id BIGSERIAL PRIMARY KEY,
            email CITEXT NOT NULL,
            password_hash TEXT NOT NULL,
            full_name TEXT NOT NULL,
            role user_role NOT NULL,
            department_id BIGINT REFERENCES departments(id) ON DELETE SET NULL,
            group_id BIGINT REFERENCES groups(id) ON DELETE SET NULL,
            status user_status NOT NULL DEFAULT 'active',
            presence user_presence NOT NULL DEFAULT 'offline',
            availability user_availability NOT NULL DEFAULT 'available',
            last_seen_at TIMESTAMPTZ,
            created_by BIGINT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_users_email UNIQUE (email),
            CONSTRAINT ck_users_role_org CHECK (
                (role = 'user' AND group_id IS NOT NULL)
                OR (role = 'senior' AND department_id IS NOT NULL AND group_id IS NULL)
                OR (role = 'admin' AND department_id IS NULL AND group_id IS NULL)
            )
        )
        """
    )
    op.execute("CREATE INDEX idx_users_email ON users (email)")
    op.execute("CREATE INDEX idx_users_department_id ON users (department_id)")
    op.execute("CREATE INDEX idx_users_group_id ON users (group_id)")
    op.execute("CREATE INDEX idx_users_role ON users (role)")

    op.execute(
        """
        CREATE TABLE user_sessions (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            jti TEXT NOT NULL,
            refresh_token_hash TEXT NOT NULL,
            ip INET,
            user_agent TEXT,
            expires_at TIMESTAMPTZ NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_user_sessions_jti UNIQUE (jti)
        )
        """
    )
    op.execute("CREATE INDEX idx_user_sessions_user_id ON user_sessions (user_id)")
    op.execute("CREATE INDEX idx_user_sessions_expires_at ON user_sessions (expires_at)")

    op.execute(
        """
        CREATE TABLE refresh_tokens (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            jti TEXT NOT NULL,
            refresh_token_hash TEXT NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL,
            revoked_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_refresh_tokens_jti UNIQUE (jti)
        )
        """
    )
    op.execute("CREATE INDEX idx_refresh_tokens_user_id ON refresh_tokens (user_id)")
    op.execute("CREATE INDEX idx_refresh_tokens_expires_at ON refresh_tokens (expires_at)")

    op.execute(
        """
        ALTER TABLE departments
            ADD CONSTRAINT fk_departments_head_user_id
            FOREIGN KEY (head_user_id) REFERENCES users(id) ON DELETE SET NULL
        """
    )
    op.execute(
        """
        ALTER TABLE departments
            ADD CONSTRAINT fk_departments_created_by
            FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
        """
    )
    op.execute(
        """
        ALTER TABLE groups
            ADD CONSTRAINT fk_groups_created_by
            FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
        """
    )
    op.execute(
        """
        ALTER TABLE users
            ADD CONSTRAINT fk_users_created_by
            FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
        """
    )

    for table in _TABLES_WITH_TIMESTAMPS:
        op.execute(
            f"""
            CREATE TRIGGER trg_{table}_updated_at
            BEFORE UPDATE ON {table}
            FOR EACH ROW
            EXECUTE FUNCTION update_timestamp_trigger()
            """
        )


def downgrade() -> None:
    for table in reversed(_TABLES_WITH_TIMESTAMPS):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_updated_at ON {table}")

    op.execute("DROP TABLE IF EXISTS refresh_tokens")
    op.execute("DROP TABLE IF EXISTS user_sessions")

    op.execute("ALTER TABLE departments DROP CONSTRAINT IF EXISTS fk_departments_head_user_id")
    op.execute("ALTER TABLE departments DROP CONSTRAINT IF EXISTS fk_departments_created_by")
    op.execute("ALTER TABLE groups DROP CONSTRAINT IF EXISTS fk_groups_created_by")
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS fk_users_created_by")

    op.execute("DROP TABLE IF EXISTS users")
    op.execute("DROP TABLE IF EXISTS groups")
    op.execute("DROP TABLE IF EXISTS departments")
    op.execute("DROP FUNCTION IF EXISTS update_timestamp_trigger()")

    for name, _ in reversed(_USER_ENUMS):
        op.execute(f"DROP TYPE IF EXISTS {name}")
