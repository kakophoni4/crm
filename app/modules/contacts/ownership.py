from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import bindparam, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.chats.timeutil import utc_now
from app.modules.db.models.contact_group_assignment import ContactGroupAssignment
from app.modules.db.models.enums import UserAvailability, UserStatus
from app.modules.db.models.group import Group
from app.modules.db.models.user import User
from app.modules.db.models.user_group_membership import UserGroupMembership
from app.modules.leads.department_inbox import DEPT_INBOX_GROUP_NAME
from app.modules.users.memberships import list_user_group_ids
from app.modules.rbac.scope import SCOPE_ALL, ScopeContext, visible_group_ids
from app.shared.settings import settings

ASSIGNMENT_AUTO_ROUND_ROBIN = "auto_round_robin"
ASSIGNMENT_AUTO_FIRST_RESPONDER = "auto_first_responder"
ASSIGNMENT_AUTO_RANDOM_AVAILABLE = "auto_random_available"
ASSIGNMENT_BOT_DEFAULT_OWNER = "bot_default_owner"
ASSIGNMENT_MANUAL_CREATE = "manual_create"
ASSIGNMENT_MANUAL_TRANSFER = "manual_transfer"
ASSIGNMENT_USER_REMOVAL_REBALANCE = "user_removal_rebalance"


@dataclass(frozen=True)
class AssignmentResult:
    assignment: ContactGroupAssignment
    created: bool
    owner_user_id: int | None


async def get_assignment(
    session: AsyncSession,
    contact_id: int,
    group_id: int,
    *,
    for_update: bool = False,
) -> ContactGroupAssignment | None:
    stmt = select(ContactGroupAssignment).where(
        ContactGroupAssignment.contact_id == contact_id,
        ContactGroupAssignment.group_id == group_id,
    )
    if for_update:
        stmt = stmt.with_for_update()
    result = await session.execute(
        stmt,
    )
    return result.scalar_one_or_none()


async def get_owner(
    session: AsyncSession,
    contact_id: int,
    group_id: int,
) -> int | None:
    row = await get_assignment(session, contact_id, group_id)
    return row.owner_user_id if row is not None else None


async def _available_user_ids(session: AsyncSession, group_id: int) -> list[int]:
    """Operators eligible for new card assignment (round-robin).

    For a real group — users in that group. For department inbox synthetic group —
    all available operators in the department's real groups.
    """
    inbox_dept = await session.execute(
        select(Group.department_id).where(
            Group.id == group_id,
            Group.name == DEPT_INBOX_GROUP_NAME,
        ),
    )
    department_id = inbox_dept.scalar_one_or_none()
    if department_id is not None:
        real_groups_subq = select(Group.id).where(
            Group.department_id == department_id,
            Group.name != DEPT_INBOX_GROUP_NAME,
        )
        membership_subq = select(UserGroupMembership.user_id).where(
            UserGroupMembership.group_id.in_(real_groups_subq),
        )
        result = await session.execute(
            select(User.id)
            .where(
                User.status == UserStatus.ACTIVE,
                User.availability == UserAvailability.AVAILABLE,
                or_(
                    User.group_id.in_(real_groups_subq),
                    User.id.in_(membership_subq),
                ),
            )
            .distinct()
            .order_by(User.id),
        )
        return [int(uid) for uid in result.scalars().all()]

    membership_subq = select(UserGroupMembership.user_id).where(
        UserGroupMembership.group_id == group_id,
    )
    result = await session.execute(
        select(User.id)
        .where(
            User.status == UserStatus.ACTIVE,
            User.availability == UserAvailability.AVAILABLE,
            or_(
                User.group_id == group_id,
                User.id.in_(membership_subq),
            ),
        )
        .distinct()
        .order_by(User.id),
    )
    return [int(uid) for uid in result.scalars().all()]


async def _pick_round_robin_owner(session: AsyncSession, group_id: int) -> int | None:
    candidates = await _available_user_ids(session, group_id)
    if not candidates:
        return None

    last_row = await session.execute(
        text(
            """
            SELECT owner_user_id
            FROM contact_group_assignments
            WHERE group_id = :gid
              AND owner_user_id IS NOT NULL
            ORDER BY assigned_at DESC, id DESC
            LIMIT 1
            """
        ),
        {"gid": group_id},
    )
    last_owner = last_row.scalar_one_or_none()
    if last_owner is None or int(last_owner) not in candidates:
        return candidates[0]

    last_index = candidates.index(int(last_owner))
    return candidates[(last_index + 1) % len(candidates)]


async def pick_group_among_candidates(
    session: AsyncSession,
    candidate_group_ids: list[int],
) -> int | None:
    """Choose a real bot group for a multi-group department bot.

    Prefers groups that currently have available operators so ownership is not
    left empty when another assigned group has staff online.
    """
    if not candidate_group_ids:
        return None
    ordered = sorted({int(gid) for gid in candidate_group_ids})
    with_staff: list[int] = []
    for gid in ordered:
        if await _available_user_ids(session, gid):
            with_staff.append(gid)
    pool = with_staff or ordered

    last_row = await session.execute(
        text(
            """
            SELECT group_id
            FROM contact_group_assignments
            WHERE group_id IN :gids
              AND owner_user_id IS NOT NULL
            ORDER BY assigned_at DESC, id DESC
            LIMIT 1
            """
        ).bindparams(bindparam("gids", expanding=True)),
        {"gids": pool},
    )
    last_gid = last_row.scalar_one_or_none()
    if last_gid is None or int(last_gid) not in pool:
        return pool[0]
    last_index = pool.index(int(last_gid))
    return pool[(last_index + 1) % len(pool)]


async def pick_owner_for_group(session: AsyncSession, group_id: int) -> int | None:
    """Public wrapper for round-robin owner selection in a group."""
    return await _pick_round_robin_owner(session, group_id)


async def drop_department_inbox_assignment(
    session: AsyncSession,
    *,
    contact_id: int,
    department_id: int,
) -> None:
    """Remove synthetic inbox ownership once the card is on a real group."""
    await session.execute(
        text(
            """
            DELETE FROM contact_group_assignments cga
            USING groups g
            WHERE cga.group_id = g.id
              AND cga.contact_id = :contact_id
              AND g.department_id = :department_id
              AND g.name = :inbox_name
            """
        ),
        {
            "contact_id": contact_id,
            "department_id": department_id,
            "inbox_name": DEPT_INBOX_GROUP_NAME,
        },
    )


async def _lock_group_row(session: AsyncSession, group_id: int) -> None:
    await session.execute(
        select(Group.id).where(Group.id == group_id).with_for_update(),
    )


async def ensure_assignment(
    session: AsyncSession,
    contact_id: int,
    group_id: int,
    *,
    preferred_owner_user_id: int | None = None,
) -> AssignmentResult:
    # Serialize assignment writes in the same group to keep round-robin atomic.
    await _lock_group_row(session, group_id)
    existing = await get_assignment(
        session,
        contact_id,
        group_id,
        for_update=True,
    )
    now = utc_now()

    # Bot exclusive owner (e.g. Infosled → fixed manager): take over auto-assigned cards.
    if preferred_owner_user_id is not None:
        preferred_ok = await session.get(User, preferred_owner_user_id)
        preferred_active = (
            preferred_ok is not None and preferred_ok.status == UserStatus.ACTIVE
        )
        if preferred_active:
            if existing is not None and existing.owner_user_id == preferred_owner_user_id:
                return AssignmentResult(
                    assignment=existing,
                    created=False,
                    owner_user_id=existing.owner_user_id,
                )
            # Do not steal manually transferred cards.
            if (
                existing is not None
                and existing.owner_user_id is not None
                and existing.assignment_source
                in {ASSIGNMENT_MANUAL_TRANSFER, ASSIGNMENT_MANUAL_CREATE}
            ):
                return AssignmentResult(
                    assignment=existing,
                    created=False,
                    owner_user_id=existing.owner_user_id,
                )

            if existing is None:
                assignment = ContactGroupAssignment(
                    contact_id=contact_id,
                    group_id=group_id,
                    owner_user_id=preferred_owner_user_id,
                    assigned_at=now,
                    assignment_source=ASSIGNMENT_BOT_DEFAULT_OWNER,
                )
                session.add(assignment)
                await session.flush()
                await session.refresh(assignment)
                return AssignmentResult(
                    assignment=assignment,
                    created=True,
                    owner_user_id=preferred_owner_user_id,
                )

            existing.owner_user_id = preferred_owner_user_id
            existing.assigned_at = now
            existing.assignment_source = ASSIGNMENT_BOT_DEFAULT_OWNER
            await session.flush()
            await session.refresh(existing)
            return AssignmentResult(
                assignment=existing,
                created=False,
                owner_user_id=preferred_owner_user_id,
            )

    if existing is not None and existing.owner_user_id is not None:
        # Exclusive bot owners (Infosled → fixed manager) must not stick when the
        # same contact writes to another bot that shares the group and has no
        # default_owner — otherwise leads land on the wrong team's employee.
        if existing.assignment_source != ASSIGNMENT_BOT_DEFAULT_OWNER:
            return AssignmentResult(
                assignment=existing,
                created=False,
                owner_user_id=existing.owner_user_id,
            )

    owner_id = await _pick_round_robin_owner(session, group_id)

    if existing is None:
        assignment = ContactGroupAssignment(
            contact_id=contact_id,
            group_id=group_id,
            owner_user_id=owner_id,
            assigned_at=now,
            assignment_source=ASSIGNMENT_AUTO_ROUND_ROBIN,
        )
        session.add(assignment)
        await session.flush()
        await session.refresh(assignment)
        return AssignmentResult(
            assignment=assignment,
            created=True,
            owner_user_id=owner_id,
        )

    existing.owner_user_id = owner_id
    existing.assigned_at = now
    existing.assignment_source = ASSIGNMENT_AUTO_ROUND_ROBIN
    await session.flush()
    await session.refresh(existing)
    return AssignmentResult(
        assignment=existing,
        created=False,
        owner_user_id=owner_id,
    )


async def apply_bot_default_owner_to_existing(
    session: AsyncSession,
    *,
    bot_id: int,
    owner_user_id: int,
) -> int:
    """Reassign auto-owned cards for chats of this bot. Manual transfers stay."""
    from app.modules.db.models.chat import Chat

    result = await session.execute(
        select(Chat.contact_id, Chat.assigned_group_id)
        .where(
            Chat.bot_id == bot_id,
            Chat.assigned_group_id.is_not(None),
        )
        .distinct(),
    )
    changed = 0
    for contact_id, group_id in result.all():
        if contact_id is None or group_id is None:
            continue
        before = await get_owner(session, int(contact_id), int(group_id))
        outcome = await ensure_assignment(
            session,
            int(contact_id),
            int(group_id),
            preferred_owner_user_id=owner_user_id,
        )
        if outcome.owner_user_id == owner_user_id and before != owner_user_id:
            changed += 1
    return changed


async def set_pending_inbound(
    session: AsyncSession,
    contact_id: int,
    group_id: int,
    *,
    at: datetime | None = None,
) -> None:
    assignment = await get_assignment(session, contact_id, group_id)
    if assignment is None:
        return
    assignment.pending_inbound_at = at or utc_now()
    assignment.escalated_to_group_at = None
    assignment.staff_notify_acked_at = None
    assignment.staff_notify_acked_by = None
    assignment.staff_notify_group_senior_at = None
    assignment.staff_notify_dept_senior_at = None
    assignment.staff_notify_admin_at = None
    await session.flush()


async def clear_pending_inbound(
    session: AsyncSession,
    contact_id: int,
    group_id: int,
) -> None:
    assignment = await get_assignment(session, contact_id, group_id)
    if assignment is None:
        return
    assignment.pending_inbound_at = None
    assignment.escalated_to_group_at = None
    assignment.staff_notify_acked_at = None
    assignment.staff_notify_acked_by = None
    assignment.staff_notify_group_senior_at = None
    assignment.staff_notify_dept_senior_at = None
    assignment.staff_notify_admin_at = None
    await session.flush()
    try:
        from app.modules.notifications.service import cancel_pending_notifications

        await cancel_pending_notifications(session, contact_id=contact_id, group_id=group_id)
    except Exception:
        import structlog

        structlog.get_logger(__name__).exception(
            "cancel_pending_notifications_failed",
            contact_id=contact_id,
            group_id=group_id,
        )


async def record_owner_outbound(
    session: AsyncSession,
    contact_id: int,
    group_id: int,
    owner_user_id: int,
    *,
    at: datetime | None = None,
) -> None:
    assignment = await get_assignment(session, contact_id, group_id)
    if assignment is None or assignment.owner_user_id != owner_user_id:
        return
    now = at or utc_now()
    assignment.last_owner_response_at = now
    assignment.pending_inbound_at = None
    assignment.escalated_to_group_at = None
    assignment.staff_notify_acked_at = None
    assignment.staff_notify_acked_by = None
    assignment.staff_notify_group_senior_at = None
    assignment.staff_notify_dept_senior_at = None
    assignment.staff_notify_admin_at = None
    await session.flush()
    try:
        from app.modules.notifications.service import cancel_pending_notifications

        await cancel_pending_notifications(session, contact_id=contact_id, group_id=group_id)
    except Exception:
        import structlog

        structlog.get_logger(__name__).exception(
            "cancel_pending_notifications_failed",
            contact_id=contact_id,
            group_id=group_id,
        )


async def reassign_owner(
    session: AsyncSession,
    contact_id: int,
    group_id: int,
    new_owner_id: int,
    *,
    source: str,
) -> ContactGroupAssignment | None:
    await _lock_group_row(session, group_id)
    assignment = await get_assignment(
        session,
        contact_id,
        group_id,
        for_update=True,
    )
    if assignment is None:
        return None
    assignment.owner_user_id = new_owner_id
    assignment.assigned_at = utc_now()
    assignment.assignment_source = source
    assignment.pending_inbound_at = None
    assignment.escalated_to_group_at = None
    assignment.staff_notify_acked_at = None
    assignment.staff_notify_acked_by = None
    assignment.staff_notify_group_senior_at = None
    assignment.staff_notify_dept_senior_at = None
    assignment.staff_notify_admin_at = None
    await session.flush()
    await session.refresh(assignment)
    return assignment


async def ensure_manual_create_assignment(
    session: AsyncSession,
    *,
    contact_id: int,
    actor: User,
    ctx: ScopeContext,
) -> None:
    """Make a manually created contact visible; set owner = creating manager (incl. admin)."""
    group_ids = visible_group_ids(ctx)
    actor_groups = await list_user_group_ids(session, actor.id)

    preferred: list[int] = []
    if group_ids == SCOPE_ALL:
        preferred = list(actor_groups)
        if not preferred and actor.group_id is not None:
            preferred = [int(actor.group_id)]
        if not preferred and actor.department_id is not None:
            dept_group = await session.execute(
                select(Group.id)
                .where(
                    Group.department_id == actor.department_id,
                    Group.name != DEPT_INBOX_GROUP_NAME,
                )
                .order_by(Group.id)
                .limit(1),
            )
            gid = dept_group.scalar_one_or_none()
            if gid is not None:
                preferred = [int(gid)]
    elif isinstance(group_ids, set) and group_ids:
        preferred = [gid for gid in actor_groups if gid in group_ids]
        if not preferred:
            preferred = [min(group_ids)]
    else:
        return

    if not preferred:
        return
    group_id = preferred[0]

    existing = await get_assignment(session, contact_id, group_id)
    if existing is not None:
        if existing.owner_user_id is None:
            existing.owner_user_id = actor.id
            if not existing.assignment_source:
                existing.assignment_source = ASSIGNMENT_MANUAL_CREATE
            await session.flush()
        return

    now = utc_now()
    session.add(
        ContactGroupAssignment(
            contact_id=contact_id,
            group_id=group_id,
            owner_user_id=actor.id,
            assigned_at=now,
            assignment_source=ASSIGNMENT_MANUAL_CREATE,
        ),
    )
    await session.flush()


def ownership_v2_enabled() -> bool:
    return settings.ownership_v2
