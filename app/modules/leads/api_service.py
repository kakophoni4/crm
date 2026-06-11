from __future__ import annotations

import contextlib
from dataclasses import dataclass
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.contacts.repository import ContactRepository
from app.modules.contacts.scope_loader import ScopeLoader
from app.modules.db.models.enums import AuditAction, StatusKind, UserRole
from app.modules.db.models.lead import Lead
from app.modules.db.models.user import User
from app.modules.leads.access import actor_can_access_lead
from app.modules.leads.crm_cache import (
    contact_crm_cache_key,
    dashboard_crm_cache_key,
    get_cached_payload,
    set_cached_payload,
)
from app.modules.leads.dashboard_metrics import DashboardMetricsRepository
from app.modules.leads.dashboard_operators import OperatorDashboardRepository
from app.modules.leads.pipeline_constants import PIPELINE_LOST_CODE, PIPELINE_WON_CODE
from app.modules.leads.repository import LeadRepository
from app.modules.leads.schemas import (
    ContactCrmSummaryResponse,
    CrmDashboardSummaryResponse,
    LeadCloseRequest,
    LeadCreateRequest,
    LeadDetailResponse,
    LeadListResponse,
    LeadPatchRequest,
    OperatorDashboardKpi,
    PipelineStatusCount,
)
from app.modules.leads.serialization import to_lead_detail, to_lead_list_item
from app.modules.leads.service import LeadService
from app.modules.rbac.scope import SCOPE_ALL, ScopeContext, visible_group_ids, visible_user_ids
from app.modules.statuses.validation import ensure_status_kind
from app.realtime.events import publish
from app.shared.exceptions import Conflict, NotFound, PermissionDenied, ValidationError
from app.shared.redis import get_redis
from app.shared.settings import get_settings


@dataclass(frozen=True)
class LeadMutationResult:
    lead: Lead
    audit_payload: dict[str, Any]
    audit_action: AuditAction | None = None
    skip_audit: bool = False


def _resolve_patch_audit_action(updates: dict[str, Any]) -> AuditAction | None:
    if "comment" in updates:
        return AuditAction.LEAD_UPDATE
    has_status = "status_id" in updates
    has_fields = "title" in updates or "custom_fields" in updates
    if not has_status and not has_fields:
        return None
    if has_status and not has_fields:
        return AuditAction.LEAD_STATUS_UPDATE
    return AuditAction.LEAD_UPDATE


class LeadApiService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = LeadRepository(session)
        self._metrics = DashboardMetricsRepository(session)
        self._operator_metrics = OperatorDashboardRepository(session)
        self._contacts = ContactRepository(session)
        self._scope_loader = ScopeLoader(session)
        self._lead_service = LeadService(session)

    async def _ctx(self, actor: User) -> ScopeContext:
        return await self._scope_loader.load(actor)

    def _scoped_group_ids(self, ctx: ScopeContext) -> set[int] | None:
        groups = visible_group_ids(ctx)
        if groups == SCOPE_ALL:
            return None
        if not isinstance(groups, set):
            return set()
        return groups

    def _group_in_scope(self, ctx: ScopeContext, group_id: int) -> bool:
        groups = self._scoped_group_ids(ctx)
        return groups is None or group_id in groups

    def _ensure_group_filter(self, ctx: ScopeContext, group_id: int | None) -> None:
        if group_id is None:
            return
        if not self._group_in_scope(ctx, group_id):
            raise PermissionDenied(message="Group filter outside scope")

    async def _require_visible_contact(self, ctx: ScopeContext, contact_id: int) -> None:
        if not await self._contacts.is_visible(ctx, contact_id):
            raise NotFound(message="Contact not found")

    async def _require_lead_access(self, ctx: ScopeContext, lead: Lead | None) -> Lead:
        if lead is None:
            raise NotFound(message="Lead not found")
        if await actor_can_access_lead(self._session, ctx, lead):
            return lead
        if await self._contacts.is_visible(ctx, lead.contact_id) and self._group_in_scope(
            ctx,
            lead.group_id,
        ):
            return lead
        raise NotFound(message="Lead not found")

    def _can_create_in_group(self, actor: User, ctx: ScopeContext, group_id: int) -> bool:
        role = actor.role if isinstance(actor.role, UserRole) else UserRole(str(actor.role))
        if role == UserRole.ADMIN:
            return True
        if role == UserRole.SENIOR:
            return self._group_in_scope(ctx, group_id)
        if role == UserRole.USER:
            groups = visible_group_ids(ctx)
            if groups == SCOPE_ALL:
                return True
            return isinstance(groups, set) and group_id in groups
        return False

    async def list_contact_leads(
        self,
        actor: User,
        contact_id: int,
        *,
        group_id: int | None,
        status_id: int | None,
        open_only: bool | None,
        cursor: str | None,
        limit: int,
    ) -> LeadListResponse:
        ctx = await self._ctx(actor)
        await self._require_visible_contact(ctx, contact_id)
        self._ensure_group_filter(ctx, group_id)
        scoped = self._scoped_group_ids(ctx)
        rows, next_cursor = await self._repo.list_for_contact(
            contact_id,
            group_ids=scoped,
            group_id=group_id,
            status_id=status_id,
            open_only=open_only,
            cursor=cursor,
            limit=limit,
        )
        lead_ids = [row.id for row in rows]
        comments_map = await self._repo.list_comments_by_lead_ids(lead_ids)
        items = []
        for row in rows:
            in_scope = await actor_can_access_lead(self._session, ctx, row)
            items.append(
                to_lead_list_item(
                    row,
                    in_scope=in_scope,
                    comments=comments_map.get(row.id, []),
                ),
            )
        return LeadListResponse(items=items, next_cursor=next_cursor)

    async def get_lead(self, actor: User, lead_id: int) -> LeadDetailResponse:
        ctx = await self._ctx(actor)
        lead = await self._require_lead_access(ctx, await self._repo.get_by_id(lead_id))
        comments = await self._repo.list_comments_for_lead(lead_id)
        return to_lead_detail(lead, in_scope=True, comments=comments)

    async def _crm_cache_get(self, key: str) -> ContactCrmSummaryResponse | None:
        settings = get_settings()
        if not settings.crm_summary_cache_enabled:
            return None
        try:
            cached = await get_cached_payload(get_redis(), key)
        except Exception:
            return None
        if cached is None:
            return None
        return ContactCrmSummaryResponse.model_validate(cached)

    async def _crm_cache_set(self, key: str, payload: ContactCrmSummaryResponse) -> None:
        settings = get_settings()
        if not settings.crm_summary_cache_enabled:
            return
        try:
            await set_cached_payload(
                get_redis(),
                key,
                payload.model_dump(mode="json"),
                ttl_seconds=settings.crm_summary_cache_ttl_seconds,
            )
        except Exception:
            return

    async def get_crm_summary(self, actor: User, contact_id: int) -> ContactCrmSummaryResponse:
        ctx = await self._ctx(actor)
        contact = await self._contacts.get_by_id(contact_id)
        if contact is None or not await self._contacts.is_visible(ctx, contact_id):
            raise NotFound(message="Contact not found")

        cache_key = contact_crm_cache_key(contact_id)
        cached = await self._crm_cache_get(cache_key)
        if cached is not None:
            return cached

        prior = await self._repo.count_closed_for_contact(contact_id)
        response = ContactCrmSummaryResponse(
            prior_leads_count=prior,
            first_registered_at=contact.created_at,
        )
        await self._crm_cache_set(cache_key, response)
        return response

    async def get_dashboard_crm_summary(self, actor: User) -> CrmDashboardSummaryResponse:
        ctx = await self._ctx(actor)
        scoped = self._scoped_group_ids(ctx)
        settings = get_settings()
        cache_key = dashboard_crm_cache_key(actor.id, scoped)
        if settings.crm_summary_cache_enabled:
            try:
                cached = await get_cached_payload(get_redis(), cache_key)
                if cached is not None:
                    return CrmDashboardSummaryResponse.model_validate(cached)
            except Exception:
                pass

        open_count = await self._repo.count_open_leads(scoped)
        closed_today = await self._repo.count_closed_today(scoped)
        closed_won_today = await self._repo.count_closed_today_by_pipeline_code(
            scoped,
            PIPELINE_WON_CODE,
        )
        closed_lost_today = await self._repo.count_closed_today_by_pipeline_code(
            scoped,
            PIPELINE_LOST_CODE,
        )
        by_status = await self._repo.count_open_by_pipeline_status(scoped)
        chats_today = await self._metrics.count_chats_today(scoped)
        avg_response = await self._metrics.avg_first_response_minutes_today(scoped)
        new_clients_today = await self._contacts.count_created_today(ctx)
        by_operator: list[OperatorDashboardKpi] = []
        role = actor.role if isinstance(actor.role, UserRole) else UserRole(str(actor.role))
        if role == UserRole.SENIOR and isinstance(scoped, set) and scoped:
            visible_users = visible_user_ids(ctx)
            operator_ids = (
                sorted(visible_users)
                if isinstance(visible_users, set)
                else []
            )
            operator_rows = await self._operator_metrics.list_operator_rows(
                operator_user_ids=operator_ids,
                group_ids=scoped,
            )
            by_operator = [
                OperatorDashboardKpi(
                    user_id=row.user_id,
                    display_name=row.display_name,
                    chats_today_count=row.chats_today_count,
                    avg_response_minutes=row.avg_response_minutes,
                    closed_won_today_count=row.closed_won_today_count,
                    closed_lost_today_count=row.closed_lost_today_count,
                    open_leads_count=row.open_leads_count,
                )
                for row in operator_rows
            ]
        response = CrmDashboardSummaryResponse(
            chats_today_count=chats_today,
            avg_response_minutes=avg_response,
            closed_leads_today_count=closed_today,
            closed_won_today_count=closed_won_today,
            closed_lost_today_count=closed_lost_today,
            new_clients_today_count=new_clients_today,
            open_leads_count=open_count,
            closed_today_count=closed_today,
            by_pipeline_status=[
                PipelineStatusCount(
                    status_id=row.status_id,
                    code=row.code,
                    label=row.label,
                    count=row.count,
                )
                for row in by_status
            ],
            by_operator=by_operator,
        )
        if settings.crm_summary_cache_enabled:
            with contextlib.suppress(Exception):
                await set_cached_payload(
                    get_redis(),
                    cache_key,
                    response.model_dump(mode="json"),
                    ttl_seconds=settings.crm_summary_cache_ttl_seconds,
                )
        return response

    async def list_recent_embed(
        self,
        actor: User,
        contact_id: int,
        *,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        result = await self.list_contact_leads(
            actor,
            contact_id,
            group_id=None,
            status_id=None,
            open_only=None,
            cursor=None,
            limit=limit,
        )
        return [item.model_dump(mode="json") for item in result.items]

    async def create_manual_lead(
        self,
        actor: User,
        contact_id: int,
        body: LeadCreateRequest,
    ) -> LeadMutationResult:
        ctx = await self._ctx(actor)
        await self._require_visible_contact(ctx, contact_id)
        if not self._can_create_in_group(actor, ctx, body.group_id):
            raise PermissionDenied(message="Cannot create lead in this group")

        existing = await self._repo.get_open(contact_id, body.group_id)
        if existing is not None:
            raise Conflict(message="Open lead already exists for this contact and group")

        if body.status_id is not None:
            await ensure_status_kind(self._session, body.status_id, StatusKind.LEAD_PIPELINE)
            resolved_status_id: int = body.status_id
        else:
            default_status_id = await self._repo.get_status_id(
                code="new",
                kind=StatusKind.LEAD_PIPELINE,
            )
            if default_status_id is None:
                raise RuntimeError("lead_pipeline status 'new' is not seeded")
            resolved_status_id = default_status_id

        chat_id = await self._repo.find_chat_for_lead(
            contact_id=contact_id,
            group_id=body.group_id,
            bot_id=body.bot_id,
        )
        if chat_id is None:
            raise ValidationError(message="No chat found for contact in the specified group")

        try:
            lead = await self._repo.insert_lead(
                contact_id=contact_id,
                group_id=body.group_id,
                bot_id=body.bot_id,
                chat_id=chat_id,
                status_id=resolved_status_id,
            )
        except IntegrityError as exc:
            raise Conflict(message="Open lead already exists for this contact and group") from exc

        if body.title:
            updated = await self._repo.update_lead_fields(
                lead.id,
                title=body.title,
                only_open=True,
            )
            if updated is not None:
                lead = updated

        await self._repo.set_chat_current_lead(chat_id, lead.id)

        from app.modules.contacts.ownership import get_owner

        owner_id = await get_owner(self._session, contact_id, body.group_id)
        scope: dict[str, int] = {"group_id": body.group_id, "chat_id": chat_id}
        if owner_id is not None:
            scope["user_id"] = owner_id
        await publish(
            "lead.created",
            {
                "lead_id": lead.id,
                "contact_id": contact_id,
                "group_id": body.group_id,
                "chat_id": chat_id,
                "status_id": lead.status_id,
                "source": "manual",
            },
            scope=scope,
        )

        return LeadMutationResult(
            lead=lead,
            audit_payload={
                "contact_id": contact_id,
                "group_id": body.group_id,
                "chat_id": chat_id,
                "source": "manual",
            },
        )

    async def patch_lead(
        self,
        actor: User,
        lead_id: int,
        body: LeadPatchRequest,
    ) -> LeadMutationResult:
        ctx = await self._ctx(actor)
        lead = await self._require_lead_access(ctx, await self._repo.get_by_id(lead_id))
        if lead.closed_at is not None:
            raise ValidationError(message="Cannot update a closed lead")

        updates = body.model_dump(exclude_unset=True)
        status_id = updates.pop("status_id", None)
        title = updates.pop("title", None)
        comment_set = "comment" in updates
        comment = updates.pop("comment", None)
        custom_fields = updates.pop("custom_fields", None)

        status_change: dict[str, int] | None = None
        if status_id is not None:
            status_change = {
                "from_status_id": lead.status_id,
                "to_status_id": status_id,
            }
            lead = await self._lead_service.patch_lead_status(lead_id, status_id, actor=actor)

        merged_fields = dict(lead.custom_fields or {})
        if custom_fields is not None:
            merged_fields.update(custom_fields)
        field_updates: dict[str, Any] = {}
        if title is not None:
            field_updates["title"] = title
        if comment_set:
            if isinstance(comment, str):
                stripped = comment.strip()
                if stripped:
                    await self._repo.add_lead_comment(
                        lead_id,
                        group_id=lead.group_id,
                        body=stripped,
                        created_by=actor.id,
                    )
                    field_updates["comment"] = stripped
                else:
                    field_updates["comment"] = None
            else:
                field_updates["comment"] = None
            field_updates["comment_set"] = True
        if custom_fields is not None:
            field_updates["custom_fields"] = merged_fields

        if field_updates:
            comment_set_flag = field_updates.pop("comment_set", False)
            updated = await self._repo.update_lead_fields(
                lead_id,
                **field_updates,
                only_open=True,
                comment_set=comment_set_flag,
            )
            if updated is None:
                raise ValidationError(message="Lead is already closed")
            lead = updated

        patch_updates = body.model_dump(exclude_unset=True)
        audit_action = _resolve_patch_audit_action(patch_updates)
        audit_payload: dict[str, Any] = {"lead_id": lead_id, "updates": patch_updates}
        if status_change is not None:
            audit_payload.update(status_change)
        await self._session.flush()
        return LeadMutationResult(
            lead=lead,
            audit_payload=audit_payload,
            audit_action=audit_action,
            skip_audit=audit_action is None,
        )

    async def close_lead(self, actor: User, lead_id: int, body: LeadCloseRequest) -> Lead:
        ctx = await self._ctx(actor)
        lead = await self._require_lead_access(ctx, await self._repo.get_by_id(lead_id))
        return await self._lead_service.close_lead(
            lead.id,
            status_id=body.status_id,
            actor=actor,
        )
