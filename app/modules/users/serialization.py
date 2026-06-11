from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.db.models.user import User
from app.modules.users.memberships import list_user_group_ids
from app.modules.users.schemas import UserOut


async def user_to_out(session: AsyncSession, user: User) -> UserOut:
    group_ids = await list_user_group_ids(session, user.id)
    legacy_group_id = user.group_id
    if legacy_group_id is not None and legacy_group_id not in group_ids:
        group_ids = sorted(set(group_ids) | {int(legacy_group_id)})
    return UserOut(
        id=user.id,
        email=str(user.email),
        username=user.username,
        full_name=user.full_name,
        role=user.role,
        department_id=user.department_id,
        group_id=group_ids[0] if len(group_ids) == 1 else None,
        group_ids=group_ids,
        status=user.status,
        presence=user.presence,
        availability=user.availability,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )
