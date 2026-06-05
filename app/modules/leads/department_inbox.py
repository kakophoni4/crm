from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# One synthetic group per department for department-bot leads (v1.2, LEADS.md §7).
DEPT_INBOX_GROUP_NAME = "__department_inbox__"


async def get_or_create_department_inbox_group(
    session: AsyncSession,
    department_id: int,
    *,
    created_by: int,
) -> int:
    """Return group id used as synthetic scope for department-bot leads."""
    insert = await session.execute(
        text(
            """
            INSERT INTO groups (name, department_id, created_by)
            VALUES (:name, :dept_id, :created_by)
            ON CONFLICT (department_id, name) DO NOTHING
            RETURNING id
            """
        ),
        {
            "name": DEPT_INBOX_GROUP_NAME,
            "dept_id": department_id,
            "created_by": created_by,
        },
    )
    new_id = insert.scalar_one_or_none()
    if new_id is not None:
        return int(new_id)

    existing = await session.execute(
        text(
            """
            SELECT id FROM groups
            WHERE department_id = :dept_id AND name = :name
            LIMIT 1
            """
        ),
        {"dept_id": department_id, "name": DEPT_INBOX_GROUP_NAME},
    )
    row_id = existing.scalar_one_or_none()
    if row_id is None:
        msg = f"department inbox group missing for department_id={department_id}"
        raise RuntimeError(msg)
    return int(row_id)


async def get_department_inbox_group_id(
    session: AsyncSession,
    department_id: int,
) -> int | None:
    """Return existing inbox group id for a department (read-only)."""
    result = await session.execute(
        text(
            """
            SELECT id FROM groups
            WHERE department_id = :dept_id AND name = :name
            LIMIT 1
            """
        ),
        {"dept_id": department_id, "name": DEPT_INBOX_GROUP_NAME},
    )
    row_id = result.scalar_one_or_none()
    return int(row_id) if row_id is not None else None
