from __future__ import annotations

import random
from collections import defaultdict
from typing import Any

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.repository import AuthRepository
from app.modules.chats.timeutil import utc_now
from app.modules.contacts.ownership import (
    ASSIGNMENT_USER_REMOVAL_REBALANCE,
    reassign_owner,
)
from app.modules.contacts.scope_loader import ScopeLoader
from app.modules.db.models.contact_group_assignment import ContactGroupAssignment
from app.modules.db.models.contact_group_transfer import ContactGroupTransfer
from app.modules.db.models.department import Department
from app.modules.db.models.enums import (
    CONTACT_TRANSFER_ACTIVE_STATES,
    TransferStatus,
    UserDeletionRequestState,
    UserRole,
    UserStatus,
)
from app.modules.db.models.group import Group
from app.modules.db.models.user import User
from app.modules.db.models.user_deletion_request import UserDeletionRequest
from app.modules.rbac.scope import can_act_on_user
from app.modules.users.memberships import active_user_ids_in_group, list_user_group_ids
from app.modules.users.repository import UserRepository
from app.shared.exceptions import Conflict, NotFound, PermissionDenied, ValidationError


async def _active_group_member_ids(
    session: AsyncSession,
    group_id: int,
    *,
    exclude_user_id: int,
) -> list[int]:
    ids = await active_user_ids_in_group(
        session,
        group_id,
        roles=(UserRole.USER, UserRole.SENIOR),
    )
    return [uid for uid in ids if uid != exclude_user_id]


async def _assert_rebalance_possible(session: AsyncSession, target_user_id: int) -> None:
    gids = await session.execute(
        select(ContactGroupAssignment.group_id)
        .where(ContactGroupAssignment.owner_user_id == target_user_id)
        .distinct(),
    )
    for gid_raw in gids.scalars().all():
        gid = int(gid_raw)
        cnt = await session.scalar(
            select(func.count())
            .select_from(ContactGroupAssignment)
            .where(
                ContactGroupAssignment.owner_user_id == target_user_id,
                ContactGroupAssignment.group_id == gid,
            ),
        )
        if not cnt:
            continue
        peers = await _active_group_member_ids(session, gid, exclude_user_id=target_user_id)
        if not peers:
            raise ValidationError(
                message="Cannot approve: no active colleagues left in the group to receive cards",
                details={"group_id": gid},
            )


async def _cancel_active_transfers_for_user(session: AsyncSession, user_id: int) -> None:
    now = utc_now()
    await session.execute(
        update(ContactGroupTransfer)
        .where(
            ContactGroupTransfer.state.in_(CONTACT_TRANSFER_ACTIVE_STATES),
            or_(
                ContactGroupTransfer.from_user_id == user_id,
                ContactGroupTransfer.to_user_id == user_id,
                ContactGroupTransfer.requested_by == user_id,
            ),
        )
        .values(state=TransferStatus.CANCELLED, updated_at=now),
    )


async def _reassign_owned_cards_evenly(
    session: AsyncSession,
    *,
    target_user_id: int,
) -> int:
    result = await session.execute(
        select(ContactGroupAssignment).where(
            ContactGroupAssignment.owner_user_id == target_user_id,
        ),
    )
    rows = list(result.scalars().all())
    if not rows:
        return 0

    by_group: dict[int, list[ContactGroupAssignment]] = defaultdict(list)
    for row in rows:
        by_group[int(row.group_id)].append(row)

    touched = 0
    for group_id, assignments in by_group.items():
        peers = await _active_group_member_ids(session, group_id, exclude_user_id=target_user_id)
        random.shuffle(assignments)
        if not peers:
            for a in assignments:
                a.owner_user_id = None
                a.assignment_source = ASSIGNMENT_USER_REMOVAL_REBALANCE
                a.assigned_at = utc_now()
                touched += 1
            continue

        peer_list = list(peers)
        random.shuffle(peer_list)
        n = len(peer_list)
        for i, a in enumerate(assignments):
            new_owner = peer_list[i % n]
            await reassign_owner(
                session,
                int(a.contact_id),
                group_id,
                new_owner,
                source=ASSIGNMENT_USER_REMOVAL_REBALANCE,
            )
            touched += 1
    return touched


class UserDeletionRequestService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = UserRepository(session)
        self._auth = AuthRepository(session)

    def _actor_role(self, actor: User) -> UserRole:
        return actor.role if isinstance(actor.role, UserRole) else UserRole(str(actor.role))

    async def _get_request(self, request_id: int) -> UserDeletionRequest:
        row = await self._session.get(UserDeletionRequest, request_id)
        if row is None:
            raise NotFound(message="Deletion request not found", details={"id": request_id})
        return row

    async def create_request(
        self,
        actor: User,
        target_user_id: int,
        *,
        comment: str | None,
    ) -> UserDeletionRequest:
        if self._actor_role(actor) != UserRole.SENIOR:
            raise PermissionDenied(message="Only senior can request user deletion")
        if actor.id == target_user_id:
            raise ValidationError(message="Cannot request deletion for yourself")

        target = await self._session.get(User, target_user_id)
        if target is None:
            raise NotFound(message="User not found", details={"id": target_user_id})

        ctx = await ScopeLoader(self._session).load(actor)
        if not can_act_on_user(ctx, target):
            raise NotFound(message="User not found", details={"id": target_user_id})

        t_role = target.role if isinstance(target.role, UserRole) else UserRole(str(target.role))
        if t_role != UserRole.USER:
            raise PermissionDenied(message="Can only request deletion for operators")

        if target.status != UserStatus.ACTIVE:
            raise ValidationError(message="User is not active")
            raise PermissionDenied(message="Target user is outside your department")

        if target.group_id is None and not await list_user_group_ids(self._session, target.id):
            raise ValidationError(message="Target user has no group; reassign manually first")

        target_group_ids = await list_user_group_ids(self._session, target.id)
        for gid in target_group_ids:
            group = await self._session.get(Group, gid)
            if group is None or group.department_id != actor.department_id:
                raise PermissionDenied(message="Target group is outside your department")

        for gid in target_group_ids:
            peers = await _active_group_member_ids(
                self._session,
                gid,
                exclude_user_id=target_user_id,
            )
            if not peers:
                raise ValidationError(
                    message=(
                        "No other active operators in one of the user's groups to receive cards; "
                        "add a colleague first"
                    ),
                    details={"group_id": gid},
                )

        req = UserDeletionRequest(
            target_user_id=target_user_id,
            requested_by_user_id=actor.id,
            state=UserDeletionRequestState.PENDING,
            comment=comment.strip() if comment and comment.strip() else None,
        )
        self._session.add(req)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._repo.rollback()
            raise Conflict(
                message="A pending deletion request already exists for this user",
            ) from exc
        await self._repo.commit()
        await self._session.refresh(req)
        return req

    async def list_requests(
        self,
        actor: User,
        *,
        state: UserDeletionRequestState | None,
    ) -> list[UserDeletionRequest]:
        role = self._actor_role(actor)
        stmt = select(UserDeletionRequest).order_by(UserDeletionRequest.created_at.desc())
        if state is not None:
            stmt = stmt.where(UserDeletionRequest.state == state)
        if role == UserRole.SENIOR:
            stmt = stmt.where(UserDeletionRequest.requested_by_user_id == actor.id)
        elif role != UserRole.ADMIN:
            raise PermissionDenied()
        result = await self._session.execute(stmt.limit(200))
        return list(result.scalars().all())

    async def _disable_user_and_rebalance(self, target: User) -> None:
        if target.status != UserStatus.ACTIVE:
            raise Conflict(message="User is already inactive")

        await _assert_rebalance_possible(self._session, target.id)
        await _cancel_active_transfers_for_user(self._session, target.id)
        await _reassign_owned_cards_evenly(self._session, target_user_id=target.id)

        await self._session.execute(
            update(Department)
            .where(Department.head_user_id == target.id)
            .values(head_user_id=None),
        )
        await self._session.execute(
            update(Group).where(Group.created_by == target.id).values(created_by=None),
        )
        await self._session.execute(
            update(User).where(User.created_by == target.id).values(created_by=None),
        )

        target.status = UserStatus.DISABLED
        await self._auth.revoke_all_refresh_tokens_for_user(target.id)

    async def admin_remove_user(self, actor: User, target_user_id: int) -> User:
        if self._actor_role(actor) != UserRole.ADMIN:
            raise PermissionDenied(message="Only admin can remove users directly")

        target = await self._session.get(User, target_user_id)
        if target is None:
            raise NotFound(message="User not found", details={"id": target_user_id})

        t_role = target.role if isinstance(target.role, UserRole) else UserRole(str(target.role))
        if t_role != UserRole.USER:
            raise PermissionDenied(message="Can only remove operators")

        await self._disable_user_and_rebalance(target)
        await self._repo.commit()
        await self._session.refresh(target)
        return target

    async def approve(self, actor: User, request_id: int) -> UserDeletionRequest:
        if self._actor_role(actor) != UserRole.ADMIN:
            raise PermissionDenied(message="Only admin can approve deletion requests")

        req = await self._get_request(request_id)
        if req.state != UserDeletionRequestState.PENDING:
            raise Conflict(message="Request is not pending")

        target = await self._session.get(User, req.target_user_id)
        if target is None:
            req.state = UserDeletionRequestState.REJECTED
            req.admin_comment = "User no longer exists"
            req.decided_at = utc_now()
            req.decided_by_user_id = actor.id
            await self._repo.commit()
            raise Conflict(message="Target user no longer exists")

        try:
            await self._disable_user_and_rebalance(target)
        except Conflict:
            req.state = UserDeletionRequestState.REJECTED
            req.admin_comment = "User already inactive"
            req.decided_at = utc_now()
            req.decided_by_user_id = actor.id
            await self._repo.commit()
            raise

        now = utc_now()
        req.state = UserDeletionRequestState.APPROVED
        req.decided_at = now
        req.decided_by_user_id = actor.id

        await self._repo.commit()
        await self._session.refresh(req)
        return req

    async def reject(
        self,
        actor: User,
        request_id: int,
        *,
        admin_comment: str | None,
    ) -> UserDeletionRequest:
        if self._actor_role(actor) != UserRole.ADMIN:
            raise PermissionDenied(message="Only admin can reject deletion requests")

        req = await self._get_request(request_id)
        if req.state != UserDeletionRequestState.PENDING:
            raise Conflict(message="Request is not pending")

        req.state = UserDeletionRequestState.REJECTED
        req.decided_at = utc_now()
        req.decided_by_user_id = actor.id
        if admin_comment and admin_comment.strip():
            req.admin_comment = admin_comment.strip()
        else:
            req.admin_comment = None
        await self._repo.commit()
        await self._session.refresh(req)
        return req

    def to_dict(self, req: UserDeletionRequest) -> dict[str, Any]:
        return {
            "id": req.id,
            "target_user_id": req.target_user_id,
            "requested_by_user_id": req.requested_by_user_id,
            "state": req.state.value,
            "comment": req.comment,
            "admin_comment": req.admin_comment,
            "decided_at": req.decided_at,
            "decided_by_user_id": req.decided_by_user_id,
            "created_at": req.created_at,
            "updated_at": req.updated_at,
            "target_full_name": req.target_user.full_name if req.target_user else None,
            "requested_by_full_name": req.requested_by.full_name if req.requested_by else None,
        }
