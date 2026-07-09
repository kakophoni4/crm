from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.chats.illiquid import archive_contact_chats
from app.modules.contacts.activity_timeline import build_contact_activity
from app.modules.contacts.diff import audit_diff_payload, diff_snapshots, snapshot_contact, to_jsonb
from app.modules.contacts.group_ownership import load_group_ownership
from app.modules.contacts.linked_bots import load_contact_linked_bots
from app.modules.contacts.ownership import ensure_manual_create_assignment
from app.modules.contacts.repository import ContactRepository
from app.modules.contacts.schemas import (
    AuditEntryResponse,
    ContactActivityItemResponse,
    ContactActivityResponse,
    ContactAuditResponse,
    ContactCreateRequest,
    ContactListResponse,
    ContactUpdateRequest,
    FieldChangeResponse,
    FieldHistoryResponse,
)
from app.modules.contacts.scope_loader import ScopeLoader
from app.modules.contacts.serialization import to_contact_response
from app.modules.contacts.status_automation import (
    apply_auto_contact_status,
    validate_manual_status_change,
)
from app.modules.db.models.contact import Contact
from app.modules.db.models.contact_field_change import ContactFieldChange
from app.modules.db.models.enums import ContactStatus, UserRole
from app.modules.db.models.user import User
from app.modules.leads.api_service import LeadApiService
from app.modules.rbac.scope import SCOPE_ALL, ScopeContext, visible_user_ids
from app.shared.exceptions import NotFound, PermissionDenied, ValidationError


@dataclass(frozen=True)
class ContactMutationResult:
    contact: Contact
    audit_payload: dict[str, Any]


class ContactService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = ContactRepository(session)
        self._scope_loader = ScopeLoader(session)

    async def _ctx(self, actor: User) -> ScopeContext:
        return await self._scope_loader.load(actor)

    def _ensure_filter_in_scope(self, ctx: ScopeContext, assigned_user_id: int | None) -> None:
        if assigned_user_id is None:
            return
        scope = visible_user_ids(ctx)
        if scope == SCOPE_ALL:
            return
        if not isinstance(scope, set) or assigned_user_id not in scope:
            raise PermissionDenied(message="Assigned user is outside your scope")

    async def list_contacts(
        self,
        actor: User,
        *,
        q: str | None,
        status: ContactStatus | None,
        assigned_user_id: int | None,
        telegram_username: str | None,
        custom_field_filters: dict[str, str],
        cursor: str | None,
        limit: int,
    ) -> ContactListResponse:
        ctx = await self._ctx(actor)
        self._ensure_filter_in_scope(ctx, assigned_user_id)
        rows, next_cursor = await self._repo.list_contacts(
            ctx=ctx,
            q=q,
            status=status,
            assigned_user_id=assigned_user_id,
            telegram_username=telegram_username,
            custom_field_filters=custom_field_filters,
            cursor=cursor,
            limit=limit,
        )
        items = [to_contact_response(row, actor=actor) for row in rows]
        return ContactListResponse(items=items, next_cursor=next_cursor)

    async def get_contact(
        self,
        actor: User,
        contact_id: int,
        *,
        embed_leads: bool = False,
    ) -> dict[str, Any]:
        ctx = await self._ctx(actor)
        contact = await self._repo.get_by_id(contact_id)
        if contact is None or not await self._repo.is_visible(ctx, contact_id):
            raise NotFound(message="Contact not found")
        payload = to_contact_response(contact, actor=actor)
        ownership = await load_group_ownership(self._session, contact_id)
        payload["group_ownership"] = [item.model_dump(mode="json") for item in ownership]
        linked_bots = await load_contact_linked_bots(self._session, contact_id)
        payload["linked_bots"] = [item.model_dump(mode="json") for item in linked_bots]
        leads_api = LeadApiService(self._session)
        payload["crm_summary"] = (
            await leads_api.get_crm_summary(actor, contact_id)
        ).model_dump(mode="json")
        if embed_leads:
            payload["recent_leads"] = await leads_api.list_recent_embed(actor, contact_id, limit=5)
        return payload

    async def create_contact(
        self,
        actor: User,
        body: ContactCreateRequest,
    ) -> ContactMutationResult:
        ctx = await self._ctx(actor)
        status = body.status or ContactStatus.NEW
        contact = Contact(
            full_name=body.full_name,
            phone=body.phone,
            email=body.email,
            telegram_user_id=body.telegram_user_id,
            telegram_username=body.telegram_username,
            status=status,
            custom_fields=dict(body.custom_fields),
            assigned_department_id=body.assigned_department_id or actor.department_id,
            source=body.source,
            created_by=actor.id,
        )
        created = await self._repo.create(contact)
        await ensure_manual_create_assignment(
            self._session,
            contact_id=created.id,
            actor=actor,
            ctx=ctx,
        )
        return ContactMutationResult(
            contact=created,
            audit_payload={"after": snapshot_contact(created)},
        )

    async def update_contact(
        self,
        actor: User,
        contact_id: int,
        body: ContactUpdateRequest,
    ) -> ContactMutationResult:
        ctx = await self._ctx(actor)
        contact = await self._repo.get_by_id(contact_id)
        if contact is None or not await self._repo.is_visible(ctx, contact_id):
            raise NotFound(message="Contact not found")
        if contact.status == ContactStatus.ARCHIVED:
            raise ValidationError(message="Cannot update archived contact")

        before_snapshot = snapshot_contact(contact)
        updates = body.model_dump(exclude_unset=True)
        # Имя приходит из Telegram, через CRM не меняем.
        updates.pop("full_name", None)
        if "note" in updates:
            raw_note = updates["note"]
            if isinstance(raw_note, str) and raw_note.strip():
                updates["note"] = raw_note.strip()
            else:
                updates["note"] = None
        custom_patch = updates.pop("custom_fields", None)
        if "status" in updates:
            raw_status = updates.pop("status")
            try:
                resolved = validate_manual_status_change(contact.status, raw_status)
            except ValueError as exc:
                if str(exc) == "only_illiquid_manual":
                    raise ValidationError(
                        message="Статус клиента можно изменить только вручную на «Неликвидный»",
                    ) from exc
                raise
            if resolved is None:
                await apply_auto_contact_status(self._session, contact)
            else:
                was_disabled = contact.status == ContactStatus.DISABLED
                contact.status = resolved
                if resolved == ContactStatus.DISABLED and not was_disabled:
                    await archive_contact_chats(self._session, contact.id)
        for field, value in updates.items():
            setattr(contact, field, value)
        if custom_patch is not None:
            merged = dict(contact.custom_fields or {})
            merged.update(custom_patch)
            contact.custom_fields = merged

        after_snapshot = snapshot_contact(contact)
        field_diffs = diff_snapshots(before_snapshot, after_snapshot)
        change_rows = [
            ContactFieldChange(
                contact_id=contact.id,
                field_name=field_name,
                old_value=to_jsonb(old_val),
                new_value=to_jsonb(new_val),
                changed_by=actor.id,
            )
            for field_name, old_val, new_val in field_diffs
        ]
        if change_rows:
            await self._repo.record_field_changes(change_rows)

        updated = await self._repo.update(contact)
        return ContactMutationResult(
            contact=updated,
            audit_payload=audit_diff_payload(before_snapshot, snapshot_contact(updated)),
        )

    async def delete_contact(self, actor: User, contact_id: int) -> ContactMutationResult:
        ctx = await self._ctx(actor)
        contact = await self._repo.get_by_id(contact_id)
        if contact is None or not await self._repo.is_visible(ctx, contact_id):
            raise NotFound(message="Contact not found")
        if contact.status == ContactStatus.ARCHIVED:
            raise NotFound(message="Contact not found")

        before_snapshot = snapshot_contact(contact)
        contact.status = ContactStatus.ARCHIVED
        contact.archived_at = datetime.now(UTC)
        updated = await self._repo.update(contact)
        return ContactMutationResult(
            contact=updated,
            audit_payload={"before": before_snapshot, "after": snapshot_contact(updated)},
        )

    async def activity_history(
        self,
        actor: User,
        contact_id: int,
        *,
        limit: int = 100,
    ) -> ContactActivityResponse:
        ctx = await self._ctx(actor)
        contact = await self._repo.get_by_id(contact_id)
        if contact is None or not await self._repo.is_visible(ctx, contact_id):
            raise NotFound(message="Contact not found")

        rows = await build_contact_activity(
            self._session,
            contact_id,
            ctx=ctx,
            limit=limit,
        )
        role = actor.role if isinstance(actor.role, UserRole) else UserRole(str(actor.role))
        include_actor = role in (UserRole.ADMIN, UserRole.SENIOR)
        return ContactActivityResponse(
            items=[
                ContactActivityItemResponse(
                    id=row.id,
                    label=row.label,
                    occurred_at=row.occurred_at,
                    actor_name=row.actor_name if include_actor else None,
                )
                for row in rows
            ],
        )

    async def field_history(
        self,
        actor: User,
        contact_id: int,
        *,
        limit: int = 100,
    ) -> FieldHistoryResponse:
        ctx = await self._ctx(actor)
        contact = await self._repo.get_by_id(contact_id)
        if contact is None or not await self._repo.is_visible(ctx, contact_id):
            raise NotFound(message="Contact not found")

        rows = await self._repo.list_field_history(contact_id, ctx=ctx, limit=limit)
        items = [
            FieldChangeResponse(
                id=row.id,
                contact_id=row.contact_id,
                field_name=row.field_name,
                old_value=row.old_value,
                new_value=row.new_value,
                changed_by=row.changed_by,
                changed_at=row.changed_at,
                changer_full_name=row.changer.full_name if row.changer else None,
            )
            for row in rows
        ]
        return FieldHistoryResponse(items=items)

    async def entity_audit(
        self,
        actor: User,
        contact_id: int,
        *,
        limit: int = 100,
    ) -> ContactAuditResponse:
        ctx = await self._ctx(actor)
        contact = await self._repo.get_by_id(contact_id)
        if contact is None or not await self._repo.is_visible(ctx, contact_id):
            raise NotFound(message="Contact not found")

        rows = await self._repo.list_entity_audit(contact_id, ctx=ctx, limit=limit)
        items = [
            AuditEntryResponse(
                id=row.id,
                actor_id=row.actor_id,
                action=row.action,
                entity_type=row.entity_type,
                entity_id=row.entity_id,
                payload=dict(row.payload or {}),
                request_id=row.request_id,
                created_at=row.created_at,
            )
            for row in rows
        ]
        return ContactAuditResponse(items=items)

    async def count_field_changes(self, contact_id: int) -> int:
        return await self._repo.count_field_changes_for_contact(contact_id)
