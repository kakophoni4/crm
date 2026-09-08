from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.blacklist.schemas import BlacklistCreateRequest, BlacklistEntryResponse, BlacklistListResponse
from app.modules.db.models.blacklist_entry import BlacklistEntry
from app.modules.db.models.user import User
from app.modules.rbac.permissions import Permission
from app.shared.db import get_db
from app.shared.exceptions import Conflict, NotFound
from app.shared.security.permissions import requires_permission

router = APIRouter(prefix="/api/v1/blacklist", tags=["blacklist"])


def _normalize(kind: str, value: str) -> str:
    raw = value.strip()
    if kind == "telegram_username":
        return raw.lstrip("@").lower()
    return "".join(ch for ch in raw if ch.isdigit())


@router.get("", response_model=BlacklistListResponse)
async def list_entries(
    _: Annotated[User, Depends(requires_permission(Permission.CONTACTS_UPDATE))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BlacklistListResponse:
    rows = (await db.execute(select(BlacklistEntry).order_by(BlacklistEntry.created_at.desc()))).scalars().all()
    return BlacklistListResponse(items=[BlacklistEntryResponse.model_validate(row, from_attributes=True) for row in rows])


@router.post("", response_model=BlacklistEntryResponse, status_code=201)
async def create_entry(
    body: BlacklistCreateRequest,
    actor: Annotated[User, Depends(requires_permission(Permission.CONTACTS_UPDATE))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BlacklistEntryResponse:
    value = _normalize(body.kind, body.value)
    if not value:
        raise Conflict(message="Укажите Telegram-ник или ИНН")
    existing = await db.scalar(select(BlacklistEntry).where(BlacklistEntry.kind == body.kind, BlacklistEntry.value == value))
    if existing is not None:
        raise Conflict(message="Эта запись уже есть в чёрном списке")
    row = BlacklistEntry(kind=body.kind, value=value, reason=body.reason.strip(), created_by=actor.id)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return BlacklistEntryResponse.model_validate(row, from_attributes=True)


@router.delete("/{entry_id}", status_code=204)
async def delete_entry(
    entry_id: int,
    _: Annotated[User, Depends(requires_permission(Permission.CONTACTS_UPDATE))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    row = await db.get(BlacklistEntry, entry_id)
    if row is None:
        raise NotFound(message="Запись ЧС не найдена")
    await db.delete(row)
    await db.commit()
