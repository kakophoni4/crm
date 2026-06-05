from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.contacts.schemas_transfer import GroupOwnershipItem
from app.modules.db.models.contact_group_assignment import ContactGroupAssignment
from app.modules.db.models.group import Group


async def load_group_ownership(
    session: AsyncSession,
    contact_id: int,
) -> list[GroupOwnershipItem]:
    result = await session.execute(
        select(ContactGroupAssignment, Group.name)
        .join(Group, Group.id == ContactGroupAssignment.group_id)
        .where(ContactGroupAssignment.contact_id == contact_id)
        .order_by(ContactGroupAssignment.group_id),
    )
    items: list[GroupOwnershipItem] = []
    for assignment, group_name in result.all():
        owner = assignment.owner_user
        items.append(
            GroupOwnershipItem(
                group_id=assignment.group_id,
                group_name=group_name,
                owner_user_id=assignment.owner_user_id,
                owner_full_name=owner.full_name if owner is not None else None,
                pending_inbound_at=assignment.pending_inbound_at,
                escalated_at=assignment.escalated_to_group_at,
            ),
        )
    return items
