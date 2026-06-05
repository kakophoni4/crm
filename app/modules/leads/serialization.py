from __future__ import annotations

from app.modules.db.models.lead import Lead
from app.modules.db.models.lead_comment import LeadComment
from app.modules.leads.schemas import (
    LeadCommentItemResponse,
    LeadDetailResponse,
    LeadListItemResponse,
)


def _comment_items(rows: list[LeadComment] | None) -> list[LeadCommentItemResponse]:
    if not rows:
        return []
    return [
        LeadCommentItemResponse(id=row.id, body=row.body, created_at=row.created_at)
        for row in rows
    ]


def _resolved_comments(
    lead: Lead,
    rows: list[LeadComment] | None,
) -> list[LeadCommentItemResponse]:
    items = _comment_items(rows)
    legacy = (lead.comment or "").strip()
    if legacy and not any(item.body == legacy for item in items):
        items.append(
            LeadCommentItemResponse(
                id=-int(lead.id),
                body=legacy,
                created_at=lead.updated_at,
            ),
        )
    return items


def to_lead_list_item(
    lead: Lead,
    *,
    in_scope: bool,
    comments: list[LeadComment] | None = None,
) -> LeadListItemResponse:
    status = lead.pipeline_status if in_scope else None
    bot = lead.bot
    return LeadListItemResponse(
        id=lead.id,
        contact_id=lead.contact_id,
        group_id=lead.group_id,
        bot_id=lead.bot_id,
        chat_id=lead.chat_id,
        status_id=lead.status_id if in_scope else None,
        status_code=status.code if status is not None else None,
        status_label=status.label if status is not None else None,
        bot_name=bot.name if bot is not None else None,
        bot_code=bot.code if bot is not None else None,
        title=lead.title if in_scope else None,
        comment=lead.comment if in_scope else None,
        comments=_resolved_comments(lead, comments),
        closed_at=lead.closed_at,
        created_at=lead.created_at,
        custom_fields=dict(lead.custom_fields or {}) if in_scope else None,
    )


def to_lead_detail(
    lead: Lead,
    *,
    in_scope: bool,
    comments: list[LeadComment] | None = None,
) -> LeadDetailResponse:
    base = to_lead_list_item(lead, in_scope=in_scope, comments=comments)
    return LeadDetailResponse(
        **base.model_dump(),
        updated_at=lead.updated_at,
    )
