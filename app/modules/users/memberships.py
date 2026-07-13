from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.db.models.enums import UserRole, UserStatus
from app.modules.db.models.group import Group
from app.modules.db.models.user import User
from app.modules.db.models.user_group_membership import UserGroupMembership


async def list_user_group_ids(session: AsyncSession, user_id: int) -> list[int]:
    result = await session.execute(
        select(UserGroupMembership.group_id)
        .where(UserGroupMembership.user_id == user_id)
        .order_by(UserGroupMembership.group_id),
    )
    ids = [int(gid) for gid in result.scalars().all()]
    if ids:
        return ids
    user = await session.get(User, user_id)
    if user is not None and user.group_id is not None:
        return [int(user.group_id)]
    return []


async def user_in_group(session: AsyncSession, user_id: int, group_id: int) -> bool:
    result = await session.execute(
        select(UserGroupMembership.id)
        .where(
            UserGroupMembership.user_id == user_id,
            UserGroupMembership.group_id == group_id,
        )
        .limit(1),
    )
    if result.scalar_one_or_none() is not None:
        return True
    user = await session.get(User, user_id)
    return user is not None and user.group_id == group_id


async def active_user_ids_in_group(
    session: AsyncSession,
    group_id: int,
    *,
    roles: tuple[UserRole, ...] | None = None,
) -> list[int]:
    """Active users assigned to a group via membership or legacy group_id."""
    membership_subq = select(UserGroupMembership.user_id).where(
        UserGroupMembership.group_id == group_id,
    )
    stmt = (
        select(User.id)
        .where(
            User.status == UserStatus.ACTIVE,
            or_(
                User.group_id == group_id,
                User.id.in_(membership_subq),
            ),
        )
        .order_by(User.id)
    )
    if roles is not None:
        stmt = stmt.where(User.role.in_(roles))
    result = await session.execute(stmt)
    return [int(uid) for uid in result.scalars().all()]


async def set_user_group_memberships(
    session: AsyncSession,
    user_id: int,
    group_ids: list[int],
) -> list[int]:
    unique_ids = sorted({int(gid) for gid in group_ids if gid > 0})
    result = await session.execute(
        select(UserGroupMembership).where(UserGroupMembership.user_id == user_id),
    )
    for row in result.scalars().all():
        await session.delete(row)
    await session.flush()

    for gid in unique_ids:
        session.add(UserGroupMembership(user_id=user_id, group_id=gid))

    user = await session.get(User, user_id)
    if user is not None:
        user.group_id = unique_ids[0] if len(unique_ids) == 1 else None

    await session.flush()
    return unique_ids


async def resolve_group_department_ids(
    session: AsyncSession,
    group_ids: list[int],
) -> dict[int, int]:
    if not group_ids:
        return {}
    result = await session.execute(
        select(Group.id, Group.department_id).where(Group.id.in_(group_ids)),
    )
    return {int(row[0]): int(row[1]) for row in result.all()}
