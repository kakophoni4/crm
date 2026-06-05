"""Unified contact activity feed for the History tab."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.db.models.audit_log_entry import AuditLogEntry
from app.modules.db.models.contact_field_change import ContactFieldChange
from app.modules.db.models.contact_group_transfer import ContactGroupTransfer
from app.modules.db.models.enums import AuditAction, ContactStatus, TransferStatus
from app.modules.db.models.lead import Lead
from app.modules.db.models.status import Status
from app.modules.db.models.user import User
from app.modules.rbac.scope import SCOPE_ALL, ScopeContext, visible_group_ids

_FIELD_LABELS: dict[str, str] = {
    "note": "Пометка",
    "phone": "Телефон",
    "email": "Email",
    "telegram_username": "Telegram",
    "status": "Статус",
    "full_name": "Имя",
    "custom_fields": "Доп. поля",
}

_STATUS_LABELS: dict[str, str] = {
    ContactStatus.NEW.value: "Новый",
    ContactStatus.ACTIVE.value: "Активный",
    ContactStatus.RETURNING.value: "Повторный",
    ContactStatus.DISABLED.value: "Неликвидный",
    ContactStatus.MERGED.value: "Объединён",
    ContactStatus.ARCHIVED.value: "В архиве",
}


@dataclass(frozen=True, slots=True)
class ActivityItem:
    id: str
    label: str
    occurred_at: datetime
    actor_name: str | None = None


def _user_name(user: Any | None) -> str | None:
    if user is None:
        return None
    name = getattr(user, "full_name", None)
    if isinstance(name, str) and name.strip():
        return name.strip()
    username = getattr(user, "username", None)
    if isinstance(username, str) and username.strip():
        return username.strip()
    email = getattr(user, "email", None)
    if isinstance(email, str) and email.strip():
        return email.strip()
    user_id = getattr(user, "id", None)
    return f"#{user_id}" if user_id is not None else None


def _actor_from_payload(
    payload: dict[str, Any],
    *,
    user_names: dict[int, str],
) -> str | None:
    for key in ("closed_by_user_id", "actor_user_id", "user_id", "changed_by"):
        raw = payload.get(key)
        if raw is None:
            continue
        try:
            user_id = int(raw)
        except (TypeError, ValueError):
            continue
        return user_names.get(user_id) or f"#{user_id}"
    return None


def _actor_from_audit(
    audit: AuditLogEntry,
    *,
    user_names: dict[int, str],
) -> str | None:
    name = _user_name(audit.actor)
    if name is not None:
        return name
    if audit.actor_id is not None:
        return user_names.get(int(audit.actor_id)) or f"#{audit.actor_id}"
    return _actor_from_payload(audit.payload or {}, user_names=user_names)


async def _load_user_names(session: AsyncSession, user_ids: set[int]) -> dict[int, str]:
    if not user_ids:
        return {}
    result = await session.execute(
        select(User.id, User.full_name, User.username, User.email).where(User.id.in_(user_ids)),
    )
    names: dict[int, str] = {}
    for row in result.all():
        label = _user_name(row)
        if label is not None:
            names[int(row.id)] = label
    return names


def _collect_user_ids_from_audits(audits_by_lead: dict[int, list[AuditLogEntry]]) -> set[int]:
    ids: set[int] = set()
    for audits in audits_by_lead.values():
        for audit in audits:
            if audit.actor_id is not None:
                ids.add(int(audit.actor_id))
            payload = audit.payload or {}
            for key in ("closed_by_user_id", "actor_user_id", "user_id", "changed_by"):
                raw = payload.get(key)
                if raw is not None:
                    try:
                        ids.add(int(raw))
                    except (TypeError, ValueError):
                        continue
    return ids


def _format_value(field_name: str, value: Any | None) -> str:
    if value is None:
        return "—"
    if field_name == "status":
        raw = value.value if hasattr(value, "value") else str(value)
        return _STATUS_LABELS.get(raw, raw)
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    text = str(value).strip()
    return text if text else "—"


def field_change_activity_item(row: ContactFieldChange) -> ActivityItem:
    field_label = _FIELD_LABELS.get(row.field_name, row.field_name)
    old_text = _format_value(row.field_name, row.old_value)
    new_text = _format_value(row.field_name, row.new_value)
    return ActivityItem(
        id=f"contact:change:{row.id}",
        label=f"Изменено «{field_label}»: {old_text} → {new_text}",
        occurred_at=row.changed_at,
        actor_name=_user_name(row.changer),
    )


def _group_suffix(lead: Lead) -> str:
    if lead.group is not None and lead.group.name:
        return f" ({lead.group.name})"
    return ""


def _status_change_label(
    payload: dict[str, Any],
    *,
    status_labels: dict[int, str],
    group_suffix: str,
) -> str | None:
    from_id = payload.get("from_status_id")
    to_id = payload.get("to_status_id")
    updates = payload.get("updates") or {}
    if to_id is None and "status_id" in updates:
        to_id = updates.get("status_id")

    from_label = payload.get("from_status_label")
    to_label = payload.get("to_status_label") or payload.get("status_label") or payload.get("label")

    if from_id is not None and from_label is None:
        from_label = status_labels.get(int(from_id))
    if to_id is not None and to_label is None:
        to_label = status_labels.get(int(to_id))

    if from_label and to_label and from_label != to_label:
        return f"Этап сделки{group_suffix}: {from_label} → {to_label}"
    if to_label:
        return f"Этап сделки{group_suffix}: {to_label}"
    if "status_id" in updates or to_id is not None:
        return f"Этап сделки{group_suffix} изменён"
    return None


def lead_activity_items(
    lead: Lead,
    audits: list[AuditLogEntry],
    *,
    status_labels: dict[int, str],
    user_names: dict[int, str],
) -> list[ActivityItem]:
    group_suffix = _group_suffix(lead)
    items: list[ActivityItem] = []
    has_create = False
    has_close = False

    for audit in audits:
        action = (
            audit.action
            if isinstance(audit.action, AuditAction)
            else AuditAction(str(audit.action))
        )
        if action == AuditAction.LEAD_STATUS_UPDATE:
            label = _status_change_label(
                audit.payload or {},
                status_labels=status_labels,
                group_suffix=group_suffix,
            )
            if label is None:
                continue
            items.append(
                ActivityItem(
                    id=f"lead:{lead.id}:status:audit:{audit.id}",
                    label=label,
                    occurred_at=audit.created_at,
                    actor_name=_actor_from_audit(audit, user_names=user_names),
                ),
            )
        elif action == AuditAction.LEAD_CREATE:
            has_create = True
            items.append(
                ActivityItem(
                    id=f"lead:{lead.id}:created:audit:{audit.id}",
                    label=f"Сделка открыта{group_suffix}",
                    occurred_at=audit.created_at,
                    actor_name=_actor_from_audit(audit, user_names=user_names),
                ),
            )
        elif action == AuditAction.LEAD_CLOSE:
            has_close = True
            items.append(
                ActivityItem(
                    id=f"lead:{lead.id}:closed:audit:{audit.id}",
                    label=f"Сделка закрыта{group_suffix}",
                    occurred_at=audit.created_at,
                    actor_name=_actor_from_audit(audit, user_names=user_names),
                ),
            )

    if not has_create:
        items.append(
            ActivityItem(
                id=f"lead:{lead.id}:opened",
                label=f"Сделка открыта{group_suffix}",
                occurred_at=lead.created_at,
                actor_name=None,
            ),
        )

    if lead.closed_at is not None and not has_close:
        items.append(
            ActivityItem(
                id=f"lead:{lead.id}:closed",
                label=f"Сделка закрыта{group_suffix}",
                occurred_at=lead.closed_at,
                actor_name=None,
            ),
        )

    return items


def transfer_activity_items(transfer: ContactGroupTransfer) -> list[ActivityItem]:
    state = (
        transfer.state
        if isinstance(transfer.state, TransferStatus)
        else TransferStatus(str(transfer.state))
    )
    from_name = _user_name(transfer.from_user) or "—"
    to_name = _user_name(transfer.to_user) or "—"
    requester = _user_name(transfer.requester)

    items = [
        ActivityItem(
            id=f"transfer:{transfer.id}:requested",
            label=f"Запрошена передача карточки: {from_name} → {to_name}",
            occurred_at=transfer.created_at,
            actor_name=requester,
        ),
    ]
    if state == TransferStatus.ACCEPTED and transfer.recipient_decided_at is not None:
        items.append(
            ActivityItem(
                id=f"transfer:{transfer.id}:accepted",
                label=f"Передача выполнена: {from_name} → {to_name}",
                occurred_at=transfer.recipient_decided_at,
                actor_name=_user_name(transfer.to_user),
            ),
        )
    elif state in (
        TransferStatus.DECLINED_SENIOR,
        TransferStatus.DECLINED_RECIPIENT,
        TransferStatus.DECLINED,
    ):
        decided_at = (
            transfer.recipient_decided_at
            or transfer.senior_decided_at
            or transfer.updated_at
        )
        if state == TransferStatus.DECLINED_SENIOR:
            actor = transfer.senior_user
        else:
            actor = transfer.to_user
        items.append(
            ActivityItem(
                id=f"transfer:{transfer.id}:declined",
                label=f"Передача отклонена: {from_name} → {to_name}",
                occurred_at=decided_at,
                actor_name=_user_name(actor),
            ),
        )
    elif state == TransferStatus.CANCELLED:
        items.append(
            ActivityItem(
                id=f"transfer:{transfer.id}:cancelled",
                label=f"Передача отменена: {from_name} → {to_name}",
                occurred_at=transfer.updated_at,
                actor_name=requester,
            ),
        )
    elif state == TransferStatus.EXPIRED:
        items.append(
            ActivityItem(
                id=f"transfer:{transfer.id}:expired",
                label=f"Срок передачи истёк: {from_name} → {to_name}",
                occurred_at=transfer.updated_at,
                actor_name=None,
            ),
        )
    return items


def _scoped_group_filter(ctx: ScopeContext) -> set[int] | None:
    groups = visible_group_ids(ctx)
    if groups == SCOPE_ALL:
        return None
    if not isinstance(groups, set) or not groups:
        return set()
    return groups


async def _load_lead_audits(
    session: AsyncSession,
    lead_ids: list[int],
) -> dict[int, list[AuditLogEntry]]:
    if not lead_ids:
        return {}
    result = await session.execute(
        select(AuditLogEntry)
        .options(selectinload(AuditLogEntry.actor))
        .where(
            AuditLogEntry.entity_type == "lead",
            AuditLogEntry.entity_id.in_(lead_ids),
            AuditLogEntry.action.in_(
                (
                    AuditAction.LEAD_CREATE,
                    AuditAction.LEAD_CLOSE,
                    AuditAction.LEAD_STATUS_UPDATE,
                ),
            ),
        )
        .order_by(AuditLogEntry.created_at.asc(), AuditLogEntry.id.asc()),
    )
    rows = list(result.scalars().all())
    by_lead: dict[int, list[AuditLogEntry]] = {}
    for row in rows:
        by_lead.setdefault(int(row.entity_id), []).append(row)
    return by_lead


def _audit_action(audit: AuditLogEntry) -> AuditAction:
    if isinstance(audit.action, AuditAction):
        return audit.action
    return AuditAction(str(audit.action))


def _collect_status_ids_from_audits(audits_by_lead: dict[int, list[AuditLogEntry]]) -> set[int]:
    ids: set[int] = set()
    for audits in audits_by_lead.values():
        for audit in audits:
            if _audit_action(audit) != AuditAction.LEAD_STATUS_UPDATE:
                continue
            payload = audit.payload or {}
            for key in ("from_status_id", "to_status_id"):
                raw = payload.get(key)
                if raw is not None:
                    ids.add(int(raw))
            updates = payload.get("updates") or {}
            raw_status = updates.get("status_id")
            if raw_status is not None:
                ids.add(int(raw_status))
    return ids


async def _load_pipeline_status_labels(
    session: AsyncSession,
    status_ids: set[int],
) -> dict[int, str]:
    if not status_ids:
        return {}
    result = await session.execute(
        select(Status.id, Status.label).where(Status.id.in_(status_ids)),
    )
    return {int(row.id): str(row.label) for row in result.all()}


async def build_contact_activity(
    session: AsyncSession,
    contact_id: int,
    *,
    ctx: ScopeContext,
    limit: int,
) -> list[ActivityItem]:
    scoped_groups = _scoped_group_filter(ctx)

    lead_stmt = select(Lead).options(selectinload(Lead.group)).where(Lead.contact_id == contact_id)
    if scoped_groups is not None:
        if not scoped_groups:
            leads: list[Lead] = []
        else:
            lead_stmt = lead_stmt.where(Lead.group_id.in_(scoped_groups))
            leads = list((await session.execute(lead_stmt)).scalars().all())
    else:
        leads = list((await session.execute(lead_stmt)).scalars().all())

    transfer_stmt = (
        select(ContactGroupTransfer)
        .options(
            selectinload(ContactGroupTransfer.from_user),
            selectinload(ContactGroupTransfer.to_user),
            selectinload(ContactGroupTransfer.requester),
            selectinload(ContactGroupTransfer.senior_user),
        )
        .where(ContactGroupTransfer.contact_id == contact_id)
    )
    if scoped_groups is not None:
        if not scoped_groups:
            transfers: list[ContactGroupTransfer] = []
        else:
            transfer_stmt = transfer_stmt.where(ContactGroupTransfer.group_id.in_(scoped_groups))
            transfers = list((await session.execute(transfer_stmt)).scalars().all())
    else:
        transfers = list((await session.execute(transfer_stmt)).scalars().all())

    change_rows = list(
        (
            await session.execute(
                select(ContactFieldChange)
                .options(selectinload(ContactFieldChange.changer))
                .where(ContactFieldChange.contact_id == contact_id)
                .order_by(ContactFieldChange.changed_at.desc()),
            )
        ).scalars().all(),
    )

    lead_audits = await _load_lead_audits(session, [lead.id for lead in leads])
    status_label_map = await _load_pipeline_status_labels(
        session,
        _collect_status_ids_from_audits(lead_audits),
    )
    actor_user_ids = _collect_user_ids_from_audits(lead_audits)
    for row in change_rows:
        actor_user_ids.add(int(row.changed_by))
    user_names = await _load_user_names(session, actor_user_ids)

    items: list[ActivityItem] = []
    for lead in leads:
        items.extend(
            lead_activity_items(
                lead,
                lead_audits.get(lead.id, []),
                status_labels=status_label_map,
                user_names=user_names,
            ),
        )
    for transfer in transfers:
        items.extend(transfer_activity_items(transfer))
    for row in change_rows:
        item = field_change_activity_item(row)
        if item.actor_name is None:
            item = ActivityItem(
                id=item.id,
                label=item.label,
                occurred_at=item.occurred_at,
                actor_name=user_names.get(int(row.changed_by)),
            )
        items.append(item)

    items.sort(key=lambda row: row.occurred_at, reverse=True)
    return items[:limit]
