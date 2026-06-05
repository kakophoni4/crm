from __future__ import annotations

from typing import Any

from app.modules.contacts.schemas import ContactResponse
from app.modules.db.models.contact import Contact
from app.modules.db.models.enums import ContactStatus, UserRole
from app.modules.db.models.user import User
from app.modules.rbac.permissions import Permission
from app.modules.rbac.role_map import has_permission


def can_see_telegram_user_id(actor: User) -> bool:
    role = actor.role if isinstance(actor.role, UserRole) else UserRole(str(actor.role))
    return has_permission(role, Permission.CONTACTS_READ_TG_ID)


def to_contact_response(contact: Contact, *, actor: User) -> dict[str, Any]:
    status = (
        contact.status
        if isinstance(contact.status, ContactStatus)
        else ContactStatus(str(contact.status))
    )
    payload = ContactResponse(
        id=contact.id,
        full_name=contact.full_name,
        note=contact.note,
        phone=contact.phone,
        email=str(contact.email) if contact.email is not None else None,
        telegram_username=(
            str(contact.telegram_username) if contact.telegram_username is not None else None
        ),
        status=status,
        custom_fields=dict(contact.custom_fields or {}),
        assigned_department_id=contact.assigned_department_id,
        source=contact.source,
        archived_at=contact.archived_at,
        created_by=contact.created_by,
        created_at=contact.created_at,
        updated_at=contact.updated_at,
    ).model_dump(mode="json")
    if can_see_telegram_user_id(actor) and contact.telegram_user_id is not None:
        payload["telegram_user_id"] = contact.telegram_user_id
    return payload
