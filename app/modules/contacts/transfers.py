from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.chats.timeutil import utc_now
from app.modules.contacts.ownership import (
    ASSIGNMENT_MANUAL_TRANSFER,
    ensure_assignment,
    get_assignment,
    reassign_owner,
)
from app.modules.contacts.realtime_payloads import contact_group_context, user_full_name
from app.modules.contacts.repository import ContactRepository
from app.modules.contacts.scope_loader import ScopeLoader
from app.modules.db.models.contact_group_transfer import ContactGroupTransfer
from app.modules.db.models.enums import (
    CONTACT_TRANSFER_ACTIVE_STATES,
    TransferStatus,
    UserRole,
)
from app.modules.db.models.group import Group
from app.modules.db.models.user import User
from app.modules.rbac.scope import SCOPE_ALL, ScopeContext, can_act_on_user, visible_group_ids
from app.realtime.events import publish
from app.shared.exceptions import Conflict, NotFound, PermissionDenied, ValidationError

TRANSFER_TTL = timedelta(days=7)


class ContactGroupTransfersService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._contacts = ContactRepository(session)
        self._scope_loader = ScopeLoader(session)

    async def _ctx(self, actor: User) -> ScopeContext:
        return await self._scope_loader.load(actor)

    async def _load_user(self, user_id: int) -> User:
        result = await self._session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is None:
            raise ValidationError(message="to_user_id not found")
        return user

    async def _load_group(self, group_id: int) -> Group:
        result = await self._session.execute(select(Group).where(Group.id == group_id))
        group = result.scalar_one_or_none()
        if group is None:
            raise NotFound(message="Group not found")
        return group

    def _ensure_group_visible(self, ctx: ScopeContext, group_id: int) -> None:
        visible = visible_group_ids(ctx)
        if visible == SCOPE_ALL:
            return
        if not isinstance(visible, set) or group_id not in visible:
            raise NotFound(message="Group not found")

    def _senior_group_in_scope(self, ctx: ScopeContext, group_id: int) -> bool:
        visible = visible_group_ids(ctx)
        if visible == SCOPE_ALL:
            return True
        return isinstance(visible, set) and group_id in visible

    async def _ensure_contact_visible(
        self,
        ctx: ScopeContext,
        contact_id: int,
    ) -> None:
        if not await self._contacts.is_contact_visible(ctx, contact_id):
            raise NotFound(message="Contact not found")

    def _actor_role(self, actor: User) -> UserRole:
        return actor.role if isinstance(actor.role, UserRole) else UserRole(str(actor.role))

    def _initial_state(self, actor: User, *, force: bool) -> TransferStatus:
        role = self._actor_role(actor)
        if force and role in (UserRole.ADMIN, UserRole.SENIOR):
            return TransferStatus.ACCEPTED
        if role in (UserRole.ADMIN, UserRole.SENIOR):
            return TransferStatus.PENDING_RECIPIENT
        return TransferStatus.PENDING_SENIOR

    async def _get_active_transfer(
        self,
        contact_id: int,
        group_id: int,
        *,
        for_update: bool = False,
    ) -> ContactGroupTransfer | None:
        stmt = select(ContactGroupTransfer).where(
            ContactGroupTransfer.contact_id == contact_id,
            ContactGroupTransfer.group_id == group_id,
            ContactGroupTransfer.state.in_(CONTACT_TRANSFER_ACTIVE_STATES),
        )
        if for_update:
            stmt = stmt.with_for_update()
        result = await self._session.execute(
            stmt,
        )
        return result.scalar_one_or_none()

    async def _get_transfer(self, transfer_id: int) -> ContactGroupTransfer:
        result = await self._session.execute(
            select(ContactGroupTransfer).where(ContactGroupTransfer.id == transfer_id),
        )
        transfer = result.scalar_one_or_none()
        if transfer is None:
            raise NotFound(message="Transfer not found")
        return transfer

    def _ensure_version(self, transfer: ContactGroupTransfer, expected_version: int | None) -> None:
        if expected_version is None:
            return
        if transfer.version != expected_version:
            raise Conflict(message="Transfer was updated by another request")

    def _bump_version(self, transfer: ContactGroupTransfer) -> None:
        transfer.version = int(transfer.version) + 1

    def _ensure_transfer_actionable(self, transfer: ContactGroupTransfer) -> None:
        state = (
            transfer.state
            if isinstance(transfer.state, TransferStatus)
            else TransferStatus(str(transfer.state))
        )
        if state == TransferStatus.EXPIRED:
            raise Conflict(message="Transfer has expired")

    async def _ensure_transfer_visible(
        self,
        ctx: ScopeContext,
        transfer: ContactGroupTransfer,
    ) -> None:
        await self._ensure_contact_visible(ctx, transfer.contact_id)
        self._ensure_group_visible(ctx, transfer.group_id)

    async def _publish_ownership_transferred(
        self,
        contact_id: int,
        group_id: int,
        *,
        from_user_id: int,
        to_user_id: int,
    ) -> None:
        to_user = await self._load_user(to_user_id)
        from_name = await user_full_name(self._session, from_user_id)
        ctx = await contact_group_context(self._session, contact_id, group_id)
        payload = {
            **ctx,
            "from_user_id": from_user_id,
            "from_user_full_name": from_name,
            "to_user_id": to_user_id,
            "to_user_full_name": to_user.full_name,
            "owner_user_id": to_user_id,
            "owner_full_name": to_user.full_name,
        }
        await publish(
            "contact.ownership.transferred",
            payload,
            scope={"group_id": group_id},
        )
        if from_user_id != to_user_id:
            await publish(
                "contact.ownership.transferred",
                {**payload, "perspective": "former_owner"},
                scope={"user_id": from_user_id},
            )
            await publish(
                "contact.ownership.transferred",
                {**payload, "perspective": "new_owner"},
                scope={"user_id": to_user_id},
            )

    async def _validate_target(
        self,
        ctx: ScopeContext,
        *,
        group_id: int,
        to_user: User,
        from_user_id: int,
    ) -> None:
        if to_user.id == from_user_id:
            raise ValidationError(message="Cannot transfer to the current owner")
        if to_user.group_id != group_id:
            raise ValidationError(message="Target user must belong to the group")
        if not can_act_on_user(ctx, to_user):
            raise PermissionDenied(message="Target user is outside your scope")

    async def request_transfer(
        self,
        actor: User,
        contact_id: int,
        group_id: int,
        *,
        to_user_id: int,
        comment: str | None,
        force: bool = False,
    ) -> tuple[ContactGroupTransfer, dict[str, Any]]:
        ctx = await self._ctx(actor)
        await self._ensure_contact_visible(ctx, contact_id)
        self._ensure_group_visible(ctx, group_id)
        await self._load_group(group_id)

        role = self._actor_role(actor)
        if force:
            if role == UserRole.ADMIN:
                pass
            elif role == UserRole.SENIOR:
                if not self._senior_group_in_scope(ctx, group_id):
                    raise PermissionDenied(
                        message="Senior can only assign cards within their department",
                    )
            else:
                raise PermissionDenied(
                    message="Only admin or senior can force-assign ownership",
                )

        # Transactional check to stay compatible until DB-level partial unique is introduced.
        active = await self._get_active_transfer(contact_id, group_id, for_update=True)
        # DB partial unique index may be missing on old environments; keep app-level guard.
        if active is not None:
            raise Conflict(message="Active transfer already exists for this contact in the group")

        assignment = await get_assignment(self._session, contact_id, group_id)
        if assignment is None:
            await ensure_assignment(self._session, contact_id, group_id)
            assignment = await get_assignment(self._session, contact_id, group_id)
        from_user_id = (
            assignment.owner_user_id
            if assignment and assignment.owner_user_id
            else actor.id
        )

        if not force and actor.id != from_user_id and role != UserRole.ADMIN:
            raise PermissionDenied(message="Only the card owner can initiate a transfer")

        to_user = await self._load_user(to_user_id)
        await self._validate_target(
            ctx,
            group_id=group_id,
            to_user=to_user,
            from_user_id=from_user_id,
        )

        now = utc_now()
        state = self._initial_state(actor, force=force)
        transfer = ContactGroupTransfer(
            contact_id=contact_id,
            group_id=group_id,
            from_user_id=from_user_id,
            to_user_id=to_user_id,
            requested_by=actor.id,
            state=state,
            force_assigned=force,
            comment=comment,
            expires_at=now + TRANSFER_TTL,
        )
        if state == TransferStatus.ACCEPTED:
            transfer.senior_user_id = actor.id
            transfer.senior_decided_at = now
            transfer.recipient_decided_at = now
            await reassign_owner(
                self._session,
                contact_id,
                group_id,
                to_user_id,
                source=ASSIGNMENT_MANUAL_TRANSFER,
            )
        elif state == TransferStatus.PENDING_RECIPIENT and role == UserRole.SENIOR:
            transfer.senior_user_id = actor.id
            transfer.senior_decided_at = now

        self._session.add(transfer)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            if "uq_cgt_active_contact_group" in str(exc.orig):
                raise Conflict(
                    message="Active transfer already exists for this contact in the group",
                ) from exc
            raise
        await self._session.refresh(transfer)

        await publish(
            "contact.transfer.requested",
            {
                "transfer_id": transfer.id,
                "contact_id": contact_id,
                "group_id": group_id,
                "from_user_id": from_user_id,
                "to_user_id": to_user_id,
                "requested_by": actor.id,
                "state": transfer.state.value,
            },
            scope={"group_id": group_id},
        )
        if state == TransferStatus.ACCEPTED:
            await self._publish_ownership_transferred(
                contact_id,
                group_id,
                from_user_id=from_user_id,
                to_user_id=to_user_id,
            )

        return transfer, {
            "transfer_id": transfer.id,
            "contact_id": contact_id,
            "group_id": group_id,
            "to_user_id": to_user_id,
            "state": transfer.state.value,
            "force": force,
        }

    async def list_transfers(
        self,
        actor: User,
        *,
        state: TransferStatus | None,
        group_id: int | None,
    ) -> list[ContactGroupTransfer]:
        ctx = await self._ctx(actor)
        role = self._actor_role(actor)
        stmt = select(ContactGroupTransfer).order_by(ContactGroupTransfer.id.desc())

        if group_id is not None:
            self._ensure_group_visible(ctx, group_id)
            stmt = stmt.where(ContactGroupTransfer.group_id == group_id)

        if state is not None:
            stmt = stmt.where(ContactGroupTransfer.state == state)

        if role == UserRole.ADMIN:
            pass
        elif role == UserRole.SENIOR:
            visible = visible_group_ids(ctx)
            if visible != SCOPE_ALL:
                if not isinstance(visible, set) or not visible:
                    return []
                stmt = stmt.where(
                    or_(
                        (
                            (ContactGroupTransfer.state == TransferStatus.PENDING_SENIOR)
                            & ContactGroupTransfer.group_id.in_(visible)
                        ),
                        ContactGroupTransfer.to_user_id == actor.id,
                        ContactGroupTransfer.requested_by == actor.id,
                    ),
                )
        else:
            stmt = stmt.where(
                (ContactGroupTransfer.to_user_id == actor.id)
                | (ContactGroupTransfer.requested_by == actor.id),
            )

        result = await self._session.execute(stmt.limit(200))
        rows = list(result.scalars().all())
        visible_rows: list[ContactGroupTransfer] = []
        for row in rows:
            try:
                await self._ensure_transfer_visible(ctx, row)
            except NotFound:
                continue
            visible_rows.append(row)
        return visible_rows

    async def approve(
        self,
        actor: User,
        transfer_id: int,
        *,
        expected_version: int | None = None,
    ) -> tuple[ContactGroupTransfer, dict[str, Any]]:
        ctx = await self._ctx(actor)
        transfer = await self._get_transfer(transfer_id)
        await self._ensure_transfer_visible(ctx, transfer)
        self._ensure_transfer_actionable(transfer)
        self._ensure_version(transfer, expected_version)
        role = self._actor_role(actor)
        if role not in (UserRole.SENIOR, UserRole.ADMIN):
            raise PermissionDenied(message="Only senior or admin can approve transfers")
        if transfer.state != TransferStatus.PENDING_SENIOR:
            raise Conflict(message="Transfer is not pending senior approval")

        now = utc_now()
        transfer.state = TransferStatus.PENDING_RECIPIENT
        transfer.senior_user_id = actor.id
        transfer.senior_decided_at = now
        self._bump_version(transfer)
        await self._session.flush()

        await publish(
            "transfer.senior_approved",
            {"transfer_id": transfer.id, "senior_id": actor.id},
            scope={"user_id": transfer.to_user_id},
        )
        return transfer, {"transfer_id": transfer.id, "state": transfer.state.value}

    async def decline(
        self,
        actor: User,
        transfer_id: int,
    ) -> tuple[ContactGroupTransfer, dict[str, Any]]:
        ctx = await self._ctx(actor)
        transfer = await self._get_transfer(transfer_id)
        await self._ensure_transfer_visible(ctx, transfer)
        self._ensure_transfer_actionable(transfer)
        role = self._actor_role(actor)
        if role not in (UserRole.SENIOR, UserRole.ADMIN):
            raise PermissionDenied(message="Only senior or admin can decline transfers")
        if transfer.state != TransferStatus.PENDING_SENIOR:
            raise Conflict(message="Transfer is not pending senior approval")

        now = utc_now()
        transfer.state = TransferStatus.DECLINED_SENIOR
        transfer.senior_user_id = actor.id
        transfer.senior_decided_at = now
        await self._session.flush()

        await publish(
            "transfer.senior_declined",
            {"transfer_id": transfer.id, "senior_id": actor.id},
            scope={"user_id": transfer.requested_by},
        )
        return transfer, {"transfer_id": transfer.id, "state": transfer.state.value}

    async def accept(
        self,
        actor: User,
        transfer_id: int,
        *,
        expected_version: int | None = None,
    ) -> tuple[ContactGroupTransfer, dict[str, Any]]:
        transfer = await self._get_transfer(transfer_id)
        self._ensure_transfer_actionable(transfer)
        self._ensure_version(transfer, expected_version)
        if transfer.to_user_id != actor.id:
            raise PermissionDenied(message="Only recipient can accept transfer")
        if transfer.state != TransferStatus.PENDING_RECIPIENT:
            raise Conflict(message="Transfer is not pending recipient acceptance")

        now = utc_now()
        transfer.state = TransferStatus.ACCEPTED
        transfer.recipient_decided_at = now
        self._bump_version(transfer)
        await reassign_owner(
            self._session,
            transfer.contact_id,
            transfer.group_id,
            transfer.to_user_id,
            source=ASSIGNMENT_MANUAL_TRANSFER,
        )
        await self._session.flush()

        await publish(
            "transfer.recipient_accepted",
            {"transfer_id": transfer.id, "recipient_id": actor.id},
            scope={"group_id": transfer.group_id},
        )
        await self._publish_ownership_transferred(
            transfer.contact_id,
            transfer.group_id,
            from_user_id=transfer.from_user_id,
            to_user_id=transfer.to_user_id,
        )
        return transfer, {
            "transfer_id": transfer.id,
            "state": transfer.state.value,
            "owner_user_id": transfer.to_user_id,
        }

    async def reject(
        self,
        actor: User,
        transfer_id: int,
    ) -> tuple[ContactGroupTransfer, dict[str, Any]]:
        transfer = await self._get_transfer(transfer_id)
        self._ensure_transfer_actionable(transfer)
        if transfer.to_user_id != actor.id:
            raise PermissionDenied(message="Only recipient can reject transfer")
        if transfer.state != TransferStatus.PENDING_RECIPIENT:
            raise Conflict(message="Transfer is not pending recipient acceptance")

        transfer.state = TransferStatus.DECLINED_RECIPIENT
        transfer.recipient_decided_at = utc_now()
        await self._session.flush()

        await publish(
            "transfer.recipient_declined",
            {"transfer_id": transfer.id, "recipient_id": actor.id},
            scope={"user_id": transfer.requested_by},
        )
        return transfer, {"transfer_id": transfer.id, "state": transfer.state.value}

    async def cancel(
        self,
        actor: User,
        transfer_id: int,
    ) -> tuple[ContactGroupTransfer, dict[str, Any]]:
        transfer = await self._get_transfer(transfer_id)
        self._ensure_transfer_actionable(transfer)
        if transfer.requested_by != actor.id:
            raise PermissionDenied(message="Only requester can cancel transfer")
        if transfer.state not in (
            TransferStatus.PENDING_SENIOR,
            TransferStatus.PENDING_RECIPIENT,
        ):
            raise Conflict(message="Only pending transfers can be cancelled")

        transfer.state = TransferStatus.CANCELLED
        await self._session.flush()

        await publish(
            "transfer.cancelled",
            {"transfer_id": transfer.id, "by_user_id": actor.id},
            scope={"group_id": transfer.group_id},
        )
        return transfer, {"transfer_id": transfer.id, "state": transfer.state.value}

    def to_response(self, transfer: ContactGroupTransfer) -> dict[str, Any]:
        state = (
            transfer.state
            if isinstance(transfer.state, TransferStatus)
            else TransferStatus(str(transfer.state))
        )
        return {
            "id": transfer.id,
            "contact_id": transfer.contact_id,
            "group_id": transfer.group_id,
            "from_user_id": transfer.from_user_id,
            "to_user_id": transfer.to_user_id,
            "requested_by": transfer.requested_by,
            "state": state.value,
            "senior_user_id": transfer.senior_user_id,
            "senior_decided_at": transfer.senior_decided_at,
            "recipient_decided_at": transfer.recipient_decided_at,
            "force_assigned": transfer.force_assigned,
            "comment": transfer.comment,
            "expires_at": transfer.expires_at,
            "version": transfer.version,
            "created_at": transfer.created_at,
            "updated_at": transfer.updated_at,
        }
